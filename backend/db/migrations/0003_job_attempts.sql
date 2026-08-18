-- ── 잡 재시도 횟수 (G0 C-2) ─────────────────────
-- stale 복구가 죽는 잡을 무한히 되살리는 걸 막는다. 3회 넘게 running 상태에서
-- heartbeat가 끊기면 더 이상 복구하지 않고 failed로 확정한다.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0;
