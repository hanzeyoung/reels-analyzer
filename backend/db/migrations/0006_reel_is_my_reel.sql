-- P5: "내 릴스" 표시. true인 행은 get_by_keyword()가 항상 제외해서
-- 같은 keyword/business_type 풀(버킷 분류·대조 분석)을 오염시키지 않는다.
ALTER TABLE reels ADD COLUMN IF NOT EXISTS is_my_reel BOOLEAN NOT NULL DEFAULT false;
