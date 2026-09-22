-- =============================================
-- Supabase 스키마 — SQL Editor에 그대로 붙여넣고 Run 하세요
-- =============================================

-- 1. 사용자 테이블 (소상공인 계정)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id UUID UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    instagram_user_id TEXT UNIQUE NOT NULL,   -- Meta에서 받은 IG 유저 ID
    username TEXT NOT NULL,
    business_type TEXT,                        -- 업종 (카페, 식당, 뷰티 등)
    access_token TEXT,                         -- Meta 사용자 토큰 (암호화 권장)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_user_id UUID UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE;

CREATE TABLE IF NOT EXISTS stores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    store_key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    business_type TEXT,
    place TEXT,
    primary_product TEXT,
    profile_data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. 릴스 원본 데이터 테이블
CREATE TABLE IF NOT EXISTS reels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instagram_media_id TEXT UNIQUE NOT NULL,   -- Meta에서 받은 미디어 ID
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    store_id UUID REFERENCES stores(id) ON DELETE SET NULL,
    business_type TEXT NOT NULL,
    permalink TEXT,                            -- 릴스 원본 링크
    thumbnail_url TEXT,
    caption TEXT,
    hashtags TEXT[],                           -- 해시태그 배열
    -- 성과 지표 (Meta Graph API raw)
    view_count INTEGER DEFAULT 0,
    like_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    save_count INTEGER DEFAULT 0,
    share_count INTEGER DEFAULT 0,
    reach INTEGER DEFAULT 0,
    duration_seconds FLOAT,                   -- 영상 길이(초)
    published_at TIMESTAMPTZ,
    collected_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE reels ADD COLUMN IF NOT EXISTS store_id UUID REFERENCES stores(id) ON DELETE SET NULL;

-- 3. 성과 스코어 테이블 (알고리즘 결과)
CREATE TABLE IF NOT EXISTS reel_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reel_id UUID REFERENCES reels(id) ON DELETE CASCADE,
    -- 스코어 산출: (조회수×0.2) + (좋아요×0.3) + (저장/공유×0.5)
    score_view FLOAT,
    score_like FLOAT,
    score_save_share FLOAT,
    total_score FLOAT NOT NULL,               -- 최종 점수
    score_tier TEXT,                          -- S / A / B / C 등급
    calculated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. AI 분석 결과 테이블 (Gemini 멀티모달 분석)
CREATE TABLE IF NOT EXISTS reel_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reel_id UUID REFERENCES reels(id) ON DELETE CASCADE,
    -- 비전 분석 결과
    camera_angles TEXT[],                     -- 탑뷰, 팔로잉샷, 클로즈업 등
    cut_speed TEXT,                           -- 느림/보통/빠름
    hook_text TEXT,                           -- 첫 3초 후킹 문구
    subtitle_position TEXT,                   -- 자막 위치
    color_tone TEXT,                          -- 색감 분위기
    -- 오디오/텍스트 분석
    bgm_mood TEXT,                            -- 음원 분위기
    caption_hooks TEXT[],                     -- 본문 후킹 패턴
    -- 가이드 생성용 요약
    analysis_summary TEXT,
    raw_gemini_response JSONB,               -- Gemini 원본 응답 저장
    category_scores JSONB,
    overall_score FLOAT,
    timeline_diagnostics JSONB,
    priority_actions TEXT[],
    analysis_basis TEXT DEFAULT 'ai_predicted',
    timeline_signals JSONB,
    signal_summary JSONB,
    prediction_confidence TEXT,
    analyzed_at TIMESTAMPTZ DEFAULT NOW()
);

-- 기존 DB에도 새 분석 컬럼을 안전하게 추가합니다.
ALTER TABLE reel_analysis ADD COLUMN IF NOT EXISTS category_scores JSONB;
ALTER TABLE reel_analysis ADD COLUMN IF NOT EXISTS overall_score FLOAT;
ALTER TABLE reel_analysis ADD COLUMN IF NOT EXISTS timeline_diagnostics JSONB;
ALTER TABLE reel_analysis ADD COLUMN IF NOT EXISTS priority_actions TEXT[];
ALTER TABLE reel_analysis ADD COLUMN IF NOT EXISTS analysis_basis TEXT DEFAULT 'ai_predicted';
ALTER TABLE reel_analysis ADD COLUMN IF NOT EXISTS timeline_signals JSONB;
ALTER TABLE reel_analysis ADD COLUMN IF NOT EXISTS signal_summary JSONB;
ALTER TABLE reel_analysis ADD COLUMN IF NOT EXISTS prediction_confidence TEXT;

-- 4-1. 게시 후 Meta 실측 스냅샷
CREATE TABLE IF NOT EXISTS reel_performance_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reel_id UUID REFERENCES reels(id) ON DELETE CASCADE,
    views INTEGER DEFAULT 0,
    reach INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    saved INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    avg_watch_time_ms BIGINT DEFAULT 0,
    total_watch_time_ms BIGINT DEFAULT 0,
    measured_score FLOAT,
    captured_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4-2. 지역·업종 경쟁 시장의 주간 스냅샷
CREATE TABLE IF NOT EXISTS market_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query TEXT NOT NULL,
    business_type TEXT,
    place TEXT,
    reel_count INTEGER DEFAULT 0,
    accounts JSONB DEFAULT '[]'::jsonb,
    top_hashtags TEXT[],
    top_tracks TEXT[],
    media JSONB DEFAULT '[]'::jsonb,
    alerts JSONB DEFAULT '[]'::jsonb,
    comparison_confidence TEXT,
    created_by UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    captured_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE market_snapshots ADD COLUMN IF NOT EXISTS media JSONB DEFAULT '[]'::jsonb;
ALTER TABLE market_snapshots ADD COLUMN IF NOT EXISTS alerts JSONB DEFAULT '[]'::jsonb;
ALTER TABLE market_snapshots ADD COLUMN IF NOT EXISTS comparison_confidence TEXT;
ALTER TABLE market_snapshots ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES auth.users(id) ON DELETE CASCADE;

-- 4-3. 내 콘텐츠에서 학습한 반복 성공 패턴
CREATE TABLE IF NOT EXISTS creator_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    sample_count INTEGER DEFAULT 0,
    top_cameras TEXT[],
    top_hooks TEXT[],
    recommended_length_sec FLOAT,
    pattern_data JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

-- 5. 트렌드 리포트 테이블 (주차별 업종별 공식)
CREATE TABLE IF NOT EXISTS trend_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_type TEXT NOT NULL,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    -- 이 주의 공식 (상위 영상 기반)
    optimal_length_sec FLOAT,                -- 최적 영상 길이
    top_camera_angles TEXT[],
    top_bgm_moods TEXT[],
    top_hook_patterns TEXT[],
    top_hashtags TEXT[],
    avg_top_score FLOAT,
    report_summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(business_type, week_start)
);

-- =============================================
-- 인덱스 (조회 성능)
-- =============================================
CREATE INDEX IF NOT EXISTS idx_reels_business_type ON reels(business_type);
CREATE INDEX IF NOT EXISTS idx_reels_store ON reels(store_id);
CREATE INDEX IF NOT EXISTS idx_reels_published_at ON reels(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_reel_scores_total ON reel_scores(total_score DESC);
CREATE INDEX IF NOT EXISTS idx_trend_reports_type_week ON trend_reports(business_type, week_start DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_reel_scores_reel_unique ON reel_scores(reel_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_reel_analysis_reel_unique ON reel_analysis(reel_id);
CREATE INDEX IF NOT EXISTS idx_performance_reel_time ON reel_performance_snapshots(reel_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_market_query_time ON market_snapshots(query, captured_at DESC);

-- =============================================
-- updated_at 자동 갱신 트리거 (users 테이블)
-- =============================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS users_updated_at ON users;
CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================
-- Row Level Security
-- 서비스 역할 키는 서버에서만 사용하고 브라우저에 노출하지 않습니다.
-- =============================================
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE stores ENABLE ROW LEVEL SECURITY;
ALTER TABLE reels ENABLE ROW LEVEL SECURITY;
ALTER TABLE reel_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE reel_analysis ENABLE ROW LEVEL SECURITY;
ALTER TABLE reel_performance_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE creator_patterns ENABLE ROW LEVEL SECURITY;
ALTER TABLE trend_reports ENABLE ROW LEVEL SECURITY;

-- The legacy token column is never populated by the application. Keep it inaccessible
-- to browser roles when upgrading an existing database.
REVOKE SELECT (access_token), INSERT (access_token), UPDATE (access_token)
    ON users FROM anon, authenticated;

DROP POLICY IF EXISTS users_self_access ON users;
CREATE POLICY users_self_access ON users
    FOR ALL USING (auth_user_id = auth.uid())
    WITH CHECK (auth_user_id = auth.uid());

DROP POLICY IF EXISTS stores_owner_access ON stores;
CREATE POLICY stores_owner_access ON stores
    FOR ALL USING (EXISTS (
        SELECT 1 FROM users WHERE users.id = stores.user_id AND users.auth_user_id = auth.uid()
    )) WITH CHECK (EXISTS (
        SELECT 1 FROM users WHERE users.id = stores.user_id AND users.auth_user_id = auth.uid()
    ));

DROP POLICY IF EXISTS reels_owner_access ON reels;
CREATE POLICY reels_owner_access ON reels
    FOR ALL USING (EXISTS (
        SELECT 1 FROM users WHERE users.id = reels.user_id AND users.auth_user_id = auth.uid()
    )) WITH CHECK (EXISTS (
        SELECT 1 FROM users WHERE users.id = reels.user_id AND users.auth_user_id = auth.uid()
    ));

DROP POLICY IF EXISTS reel_scores_owner_access ON reel_scores;
CREATE POLICY reel_scores_owner_access ON reel_scores
    FOR ALL USING (EXISTS (
        SELECT 1 FROM reels JOIN users ON users.id = reels.user_id
        WHERE reels.id = reel_scores.reel_id AND users.auth_user_id = auth.uid()
    )) WITH CHECK (EXISTS (
        SELECT 1 FROM reels JOIN users ON users.id = reels.user_id
        WHERE reels.id = reel_scores.reel_id AND users.auth_user_id = auth.uid()
    ));

DROP POLICY IF EXISTS reel_analysis_owner_access ON reel_analysis;
CREATE POLICY reel_analysis_owner_access ON reel_analysis
    FOR ALL USING (EXISTS (
        SELECT 1 FROM reels JOIN users ON users.id = reels.user_id
        WHERE reels.id = reel_analysis.reel_id AND users.auth_user_id = auth.uid()
    )) WITH CHECK (EXISTS (
        SELECT 1 FROM reels JOIN users ON users.id = reels.user_id
        WHERE reels.id = reel_analysis.reel_id AND users.auth_user_id = auth.uid()
    ));

DROP POLICY IF EXISTS reel_performance_owner_access ON reel_performance_snapshots;
CREATE POLICY reel_performance_owner_access ON reel_performance_snapshots
    FOR ALL USING (EXISTS (
        SELECT 1 FROM reels JOIN users ON users.id = reels.user_id
        WHERE reels.id = reel_performance_snapshots.reel_id AND users.auth_user_id = auth.uid()
    )) WITH CHECK (EXISTS (
        SELECT 1 FROM reels JOIN users ON users.id = reels.user_id
        WHERE reels.id = reel_performance_snapshots.reel_id AND users.auth_user_id = auth.uid()
    ));

DROP POLICY IF EXISTS creator_patterns_owner_access ON creator_patterns;
CREATE POLICY creator_patterns_owner_access ON creator_patterns
    FOR ALL USING (EXISTS (
        SELECT 1 FROM users WHERE users.id = creator_patterns.user_id AND users.auth_user_id = auth.uid()
    )) WITH CHECK (EXISTS (
        SELECT 1 FROM users WHERE users.id = creator_patterns.user_id AND users.auth_user_id = auth.uid()
    ));

DROP POLICY IF EXISTS market_snapshots_owner_access ON market_snapshots;
CREATE POLICY market_snapshots_owner_access ON market_snapshots
    FOR ALL USING (created_by = auth.uid())
    WITH CHECK (created_by = auth.uid());

DROP POLICY IF EXISTS trend_reports_authenticated_read ON trend_reports;
CREATE POLICY trend_reports_authenticated_read ON trend_reports
    FOR SELECT USING (auth.role() = 'authenticated');
