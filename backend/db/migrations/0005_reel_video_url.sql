-- ── reels.video_url (P2 T-2.1 계약 갭 해결, 2026-08-14) ────────────
-- preparing(frames.py) 단계가 mp4를 다운로드하려면 video_url이 필요한데,
-- 원래 계약 주석("video_url 저장 안 함")대로면 collect 이후 어디서도 못 구한다.
-- 워커가 단계 간 job_id로만 통신(메모리 전달 없음)하므로 DB에 저장해야 한다.
-- Instagram의 서명된 만료 URL이라 오래 지나면 무용지물일 수 있지만, 그 경우도
-- 다운로드 실패로 로그만 남기고 넘어가는 기존 실패 원칙(docs/03-pipeline.md)으로
-- 처리 가능해 컬럼 추가 쪽을 택했다.
ALTER TABLE reels ADD COLUMN IF NOT EXISTS video_url TEXT;
