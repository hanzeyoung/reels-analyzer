# 05 — API

Base: `/api`
전 응답 JSON. 에러는 `{"detail": "..."}`.

---

## POST /api/analyses

잡 생성. **동기 작업 0.** 즉시 반환한다.

**Request**
```json
{
  "keyword": "성수동카페",
  "business_type": "카페",
  "constraints": {
    "shooting_alone": true,
    "equipment": ["스마트폰"],
    "space": "좁음",
    "can_show_face": false,
    "weekly_minutes": 60
  },
  "my_reel_url": null
}
```

**Response 202**
```json
{ "job_id": "0f8c...", "status": "queued" }
```

**400** — keyword 빈 문자열, business_type 미지정

---

## GET /api/analyses/{job_id}

**Response 200 — 진행 중**
```json
{
  "job_id": "0f8c...",
  "status": "running",
  "stage": "analyzing",
  "progress": { "current": 7, "total": 20 },
  "error": null,
  "result": null
}
```

**Response 200 — 완료**
```json
{
  "job_id": "0f8c...",
  "status": "done",
  "stage": null,
  "progress": { "current": 20, "total": 20 },
  "error": null,
  "result": { ...Guide }
}
```

**Response 200 — 실패**
```json
{
  "job_id": "0f8c...",
  "status": "failed",
  "stage": "collecting",
  "error": "Apify actor run failed after 3 retries",
  "result": null
}
```

**404** — 없는 job_id

폴링 간격 권장 2초. `done`/`failed`면 중단.

---

## GET /api/analyses

최근 잡 목록. `?limit=20`

```json
{ "items": [ { "job_id": "...", "keyword": "...", "status": "done", "created_at": "..." } ] }
```

---

## POST /api/analyses/{job_id}/cancel

`queued` 또는 `running` → `failed` (`error="cancelled by user"`).
이미 `done`이면 409.

---

## GET /api/health

```json
{ "ok": true, "worker_alive": true, "last_heartbeat": "..." }
```

`worker_alive`는 **워커 프로세스 자체의 heartbeat**(`workers` 테이블, 루프마다 잡 유무와
무관하게 upsert) 기준으로 최근 60초 내 row가 있는지로 판단한다. (G0 A-2: 기존에 `jobs`
테이블의 running 잡 heartbeat로 판단하던 방식은 "실행 중인 잡이 없으면 워커가 죽어도
healthy로 보인다"는 결함이 있어서 폐기했다.)

---

## 타입 공유

FastAPI가 OpenAPI 스키마를 노출하고, 프론트는 이걸로 TS 타입을 생성한다.

```bash
make types   # openapi.json → frontend/src/api/generated/
```

`frontend/src/api/generated/`는 **손으로 편집 금지.**
