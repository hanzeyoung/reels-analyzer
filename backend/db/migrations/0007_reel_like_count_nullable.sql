-- P6.5 실측(2026-08-24): 좋아요 비공개 계정은 Apify에서 likesCount=-1로 온다.
-- 0으로 채우면 "좋아요 0개인 저성과 릴스"로 오인돼 engagement_rate가 왜곡되고
-- control 그룹에 인위적으로 쏠린다 — NULL("모른다")을 허용한다.
ALTER TABLE reels ALTER COLUMN like_count DROP NOT NULL;
ALTER TABLE reels ALTER COLUMN like_count DROP DEFAULT;

-- reel_metrics.like_count도 reels.like_count를 그대로 옮겨 담는 컬럼이라 같이 바꾼다.
ALTER TABLE reel_metrics ALTER COLUMN like_count DROP NOT NULL;
ALTER TABLE reel_metrics ALTER COLUMN like_count DROP DEFAULT;
