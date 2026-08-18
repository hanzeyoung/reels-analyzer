-- ── reels 원본 참여지표 (P1 T-1.6 계약 갭 해결, 2026-08-14) ────────────
-- score.run()이 job_id로 reels 테이블을 다시 조회해서 지표를 계산해야 하는데,
-- 원본 참여지표(좋아요/댓글/재생/공유)가 reel_metrics에만 있고 reels엔 없어서
-- collect→score 단계 분리가 성립하지 않았다. reels에도 저장한다(reel_metrics와 일부
-- 중복되지만, reel_metrics는 "측정된 파생 지표"이고 reels는 "수집된 원본"이라 의미가 다르다).
ALTER TABLE reels ADD COLUMN IF NOT EXISTS play_count INT NOT NULL DEFAULT 0;
ALTER TABLE reels ADD COLUMN IF NOT EXISTS like_count INT NOT NULL DEFAULT 0;
ALTER TABLE reels ADD COLUMN IF NOT EXISTS comment_count INT NOT NULL DEFAULT 0;
ALTER TABLE reels ADD COLUMN IF NOT EXISTS share_count INT NOT NULL DEFAULT 0;
