-- ── 잡 ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status TEXT NOT NULL DEFAULT 'queued',      -- queued|running|done|failed
    stage TEXT,                                  -- collecting|scoring|...
    progress_current INT NOT NULL DEFAULT 0,
    progress_total INT NOT NULL DEFAULT 0,
    error TEXT,
    heartbeat_at TIMESTAMPTZ,
    request JSONB NOT NULL,                      -- AnalysisRequest
    result JSONB,                                -- Guide
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_stale ON jobs(status, heartbeat_at);


-- ── 계정 ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS accounts (
    username TEXT PRIMARY KEY,
    follower_count INT,                          -- NULL 허용 = "모른다"
    fetched_at TIMESTAMPTZ                       -- 30일 캐시 판정
);


-- ── 릴스 ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS reels (
    code TEXT PRIMARY KEY,                       -- 릴스 shortcode = 기본 키
    url TEXT NOT NULL,
    username TEXT REFERENCES accounts(username),
    business_type TEXT,
    keyword TEXT,
    caption TEXT DEFAULT '',
    hashtags TEXT[] DEFAULT '{}',
    audio_title TEXT,
    thumbnail_url TEXT,
    duration_sec REAL,
    taken_at TIMESTAMPTZ NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    -- video_url 저장 안 함. mp4는 분석 후 삭제한다.
);
CREATE INDEX IF NOT EXISTS idx_reels_taken_at ON reels(taken_at DESC);
CREATE INDEX IF NOT EXISTS idx_reels_keyword ON reels(keyword, taken_at DESC);


-- ── 지표 ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS reel_metrics (
    reel_code TEXT PRIMARY KEY REFERENCES reels(code) ON DELETE CASCADE,
    play_count INT NOT NULL DEFAULT 0,
    like_count INT NOT NULL DEFAULT 0,
    comment_count INT NOT NULL DEFAULT 0,
    share_count INT NOT NULL DEFAULT 0,
    engagement_rate REAL NOT NULL,
    share_rate REAL NOT NULL,
    reach_multiple REAL,                         -- NULL = 팔로워 미상
    bucket TEXT NOT NULL DEFAULT 'unknown',
    measured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_metrics_bucket ON reel_metrics(bucket, reach_multiple DESC);


-- ── 샷 ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shot_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reel_code TEXT NOT NULL REFERENCES reels(code) ON DELETE CASCADE,
    idx INT NOT NULL,
    t_start REAL NOT NULL,                       -- ffmpeg 출처
    t_end REAL NOT NULL,
    angle TEXT,
    subject TEXT,
    on_screen_text TEXT,
    movement TEXT,
    purpose TEXT,
    technique TEXT,
    difficulty TEXT,
    requires TEXT[] DEFAULT '{}',
    solo_alternative TEXT,
    model TEXT,
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT shot_segments_reel_idx_uniq UNIQUE (reel_code, idx),
    CONSTRAINT shot_segments_time_valid CHECK (t_start < t_end)
);
CREATE INDEX IF NOT EXISTS idx_shots_reel ON shot_segments(reel_code, idx);


-- ── 릴스 단위 분석 요약 ───────────────────────
CREATE TABLE IF NOT EXISTS reel_analyses (
    reel_code TEXT PRIMARY KEY REFERENCES reels(code) ON DELETE CASCADE,
    cut_count INT NOT NULL,
    avg_shot_sec REAL NOT NULL,
    first_shot_sec REAL NOT NULL,
    caption_hooks TEXT[] DEFAULT '{}',
    color_tone TEXT,
    subtitle_position TEXT,
    summary TEXT,
    model TEXT,
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ── 생성된 가이드 ─────────────────────────────
CREATE TABLE IF NOT EXISTS guides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    business_type TEXT NOT NULL,
    keyword TEXT NOT NULL,
    week_of DATE NOT NULL,
    payload JSONB NOT NULL,                      -- Guide 전문
    confidence TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_guides_lookup ON guides(business_type, week_of DESC);


-- ── 버킷 경계 이력 ────────────────────────────
CREATE TABLE IF NOT EXISTS bucket_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_type TEXT,                          -- NULL = 전역 기본값
    boundaries JSONB NOT NULL,                   -- {"B1":1000,"B2":10000,"B3":100000}
    source TEXT NOT NULL,                        -- 'fixed' | 'percentile'
    sample_size INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ── updated_at 트리거 ─────────────────────────
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS jobs_touch ON jobs;
CREATE TRIGGER jobs_touch BEFORE UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();


-- ── 초기 버킷 경계 ────────────────────────────
INSERT INTO bucket_configs (business_type, boundaries, source)
SELECT NULL, '{"B1":1000,"B2":10000,"B3":100000}'::jsonb, 'fixed'
WHERE NOT EXISTS (SELECT 1 FROM bucket_configs WHERE business_type IS NULL);
