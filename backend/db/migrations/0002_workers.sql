-- ── 워커 프로세스 heartbeat (G0 A-2) ────────────
-- jobs.heartbeat_at은 "이 잡이 살아있는가"이고, workers.last_seen_at은
-- "워커 프로세스 자체가 살아있는가"다. 목적이 달라서 분리한다.
-- running 잡이 하나도 없어도(= 워커가 idle이어도) 워커 생존은 알 수 있어야 한다.
CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY,               -- 호스트명:PID
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_workers_last_seen ON workers(last_seen_at DESC);
