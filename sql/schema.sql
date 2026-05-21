-- =============================================
-- Supabase 스키마 — SQL Editor에 그대로 붙여넣고 Run 하세요
-- =============================================

-- 1. 사용자 테이블 (소상공인 계정)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instagram_user_id TEXT UNIQUE NOT NULL,   -- Meta에서 받은 IG 유저 ID
    username TEXT NOT NULL,
    business_type TEXT,                        -- 업종 (카페, 식당, 뷰티 등)
    access_token TEXT,                         -- Meta 사용자 토큰 (암호화 권장)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. 릴스 원본 데이터 테이블
CREATE TABLE IF NOT EXISTS reels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instagram_media_id TEXT UNIQUE NOT NULL,   -- Meta에서 받은 미디어 ID
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
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
    analyzed_at TIMESTAMPTZ DEFAULT NOW()
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
CREATE INDEX IF NOT EXISTS idx_reels_published_at ON reels(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_reel_scores_total ON reel_scores(total_score DESC);
CREATE INDEX IF NOT EXISTS idx_trend_reports_type_week ON trend_reports(business_type, week_start DESC);

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

CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
