# 01 — 아키텍처

## 왜 잡 기반인가

Apify 실행 + 영상 다운로드 + VLM 10~20회 = **5~15분**.
HTTP 요청 하나로 절대 못 버틴다. 그래서 요청은 잡만 만들고 즉시 반환한다.

```
POST /api/analyses  →  jobs 로우 생성 → 202 {job_id}  (동기 작업 0)
        ↓
   워커 프로세스가 queued 잡을 집어 단계별 실행
        ↓
GET /api/analyses/{id}  ←  프론트가 2초 폴링
```

Celery/Redis 안 쓴다. DB 테이블 + 폴링으로 충분하고, 상태가 DB에 남아서 실패 지점 추적이 쉽다.

## 프로세스 3개

| 프로세스 | 역할 |
|---|---|
| `api` | FastAPI. 잡 생성/조회만. 무거운 작업 절대 금지 |
| `worker` | 잡 실행. ffmpeg·VLM·Claude 호출은 전부 여기 |
| `frontend` | Vite dev server (프로덕션은 정적 빌드) |

## 상태 전이

```
                 ┌──────────────────────────────────────┐
                 ↓                                      │
queued ──→ collecting ──→ scoring ──→ preparing ──→ analyzing
                                                         │
                              ┌──────────────────────────┘
                              ↓
                         comparing ──→ generating ──→ done
                              
어느 단계에서든 예외 → failed (error 기록)
heartbeat_at 만료 → queued 로 복귀 (stale 복구)
```

- `status`: `queued` | `running` | `done` | `failed`
- `stage`: `running`일 때만 값이 있음. 위 6단계 중 하나
- `progress_current` / `progress_total`: 단계 내부 진행 (예: 릴스 7/20 분석 중)

## 재개 가능성 (설계의 핵심)

각 단계의 산출물을 DB에 저장한다. 중간에 죽어도 **그 단계부터** 재시작한다.

특히 `analyzing`은 릴스 단위로 커밋한다. VLM 결과가 이미 `shot_segments`에 있으면
재분석하지 않는다. **이게 비용 방어선이다.**

## stale 복구

워커가 죽으면 잡이 `analyzing`에서 영원히 멈춘다.

- 워커는 루프마다 `jobs.heartbeat_at = now()` 갱신
- 리퍼가 주기적으로 `status='running' AND heartbeat_at < now() - 5min` 인 잡을 `queued`로 되돌림
- 되돌릴 때 `stage`는 유지 → 그 단계부터 재개

**P0에서 반드시 구현한다.** 나중에 붙이면 디버깅 지옥이 된다.

## 외부 의존 격리

모든 외부 호출은 인터페이스 뒤에 있고 `fake` 짝이 있다.

| 인터페이스 | real | fake |
|---|---|---|
| `CollectProvider` | Apify REST | `fixtures/` 읽기 |
| `VisionProvider` | Claude (기본) / Gemini(자리만) | `fixtures/` 읽기 |
| `WriterProvider` | Claude | `fixtures/` 읽기 |

`APIFY_MODE` / `VISION_MODE` / `WRITER_MODE` = `fake` | `real`. **기본은 fake, 항상 fake로
유지한다.** `.env` 파일 자체를 real로 손으로 고치지 않는다 — `make dev`(운영)와
`pytest`(테스트)가 같은 `.env`를 공유해서, 손으로 바꿔놓으면 되돌리는 걸 잊는 순간
테스트가 실제 API를 호출해버린다(실제로 겪은 사고, P6.5 2026-08-24). 실측(real API로
직접 확인)이 필요하면 `backend/scripts/real_mode.sh` 진입점을 통해서만 하라 — `.env`는
안 건드리고 그 명령의 프로세스에만 real 환경변수를 준다. `pytest`는 `tests/conftest.py`의
`pytest_configure`가 세 MODE 중 하나라도 real이면 세션 자체를 실패시킨다(구조적 가드).

fixture는 손으로 쓰지 않는다. **P1에서 실제 응답을 캡처해서 박제한다.**
상상으로 만든 fixture 위에 개발하면 실키 전환 때 계약이 깨진다.

## 파일 수명

mp4는 임시 디렉토리에만 존재한다. 분석 끝나면 **즉시 삭제**.
DB에는 파생 피처(컷 경계, 샷 서술)만 남긴다.
