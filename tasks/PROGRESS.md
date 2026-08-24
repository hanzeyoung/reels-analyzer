# PROGRESS

> 페이즈 종료 시 CLI가 여기에 추가한다. 다음 세션은 `CLAUDE.md` → 이 파일 → `phase-N.md` 순으로 읽는다.
> 아래 형식을 그대로 따른다.

```markdown
## P{N} — {YYYY-MM-DD}

### 완료
- T-N.1 …

### 미완 / 보류
- T-N.4 — 이유:

### 내가 내린 판단
- {무엇을} {어떻게} — 근거:

### 명세와 어긋났던 지점
- docs/0X 의 {항목}이 {이유}로 애매했음 → {어떻게 처리}

### 다음 세션이 알아야 할 것
-
```

---

## P0 — 2026-08-06

### 완료
- T-0.1 스캐폴드: `docs/`, `tasks/`, `fixtures/`, `backend/`, `frontend/` 디렉토리를 CLAUDE.md 구조와 1:1로 맞춤. `backend/pyproject.toml`, `frontend/package.json`, `Makefile`, `.env.example`, `.gitignore` 작성.
  - `make check` (ruff + mypy + pytest, eslint + tsc) 전부 그린.
  - `pytest` 26개 중 20개 통과, 6개 스킵(DB 없음 — 아래 "미완" 참조). exit 0.
  - FastAPI 앱 `uvicorn app.main:app` 부팅 확인, `/openapi.json`에 4개 라우트 노출 확인.
- T-0.2 계약 스키마: `docs/02-contracts.md` 전 모델을 `backend/app/schemas/*.py`로 1:1 이식. 전 모델 `extra="forbid"`. `Account.follower_count: int | None = None` 확인. 계약 불변식 중 단일 모델 안에서 검증 가능한 것(`Cut`/`ShotSegment.t_start<t_end`, `FeatureCount.count<=total`, `ComparisonResult.sufficient↔findings`, `Guide.confidence↔caveat`)은 `model_validator`로 코드에 강제. `tests/schemas/test_contracts.py` 20개 전부 통과.
- T-0.3 DB 스키마: `docs/06-db.md`의 DDL을 `backend/db/migrations/0001_init.sql`로 그대로 옮김(이미 멱등하게 작성돼 있음 — `IF NOT EXISTS`/`CREATE OR REPLACE`/가드 `INSERT`). `backend/app/db/migrate.py` 러너 작성(psycopg3, 파라미터 없는 다중 statement는 simple query protocol로 한 번에 실행). 계약↔컬럼 대조표는 이미 `docs/06-db.md` 하단에 있어 추가 작업 없음.
- T-0.4 잡 시스템: `backend/app/db/jobs.py`(생성/조회/목록/claim/stage/progress/heartbeat/done/failed/cancel/stale reap), `backend/app/api/routes/analyses.py`(POST/GET/GET-list/cancel), `backend/app/api/routes/health.py`. 상태 전이·엔드포인트 응답 형태는 `docs/05-api.md`와 `docs/01-architecture.md` 그대로. `tests/api/test_jobs.py` 4개 시나리오 작성(생성/조회, 진행률, stale 복구, done 결과 저장).
- T-0.5 Provider: `backend/app/providers/{base,collect,vision,writer}.py` + 팩토리(`__init__.py`). `APIFY_MODE`/`VISION_MODE`/`WRITER_MODE` 환경변수, 기본 fake. `fixtures/{collect,vision,writer}/sample.json` 최소 골격 작성. fake 3종 로드 확인(수동 스모크 테스트 통과).
- T-0.6 워커 루프: `backend/app/pipeline/{collect,score,frames,analyze,compare,guide}.py` 6개 모듈, 전부 `run(job_id) -> None: pass`. `backend/app/worker/loop.py`(6단계 순회, 예외 시 `failed`+다음 잡 계속, stale reap 루프마다 실행), `backend/app/worker/__main__.py`, `backend/app/worker/stage_runner.py`(`make stage S=... F=...`). `tests/worker/test_loop.py` 2개 시나리오 작성.

### 미완 / 보류
- **DB 연동 테스트 전부 미실행** (`tests/api/test_jobs.py` 4개, `tests/worker/test_loop.py` 2개) — 이유: 이 샌드박스에 Postgres/Docker가 전혀 없다(`psql`, `docker` 바이너리 없음). `DATABASE_URL` 미설정 시 스킵되도록 짜놨고, 코드 자체는 리뷰 가능하지만 **실제 DB 왕복으로 검증된 적은 없다.** phase-0.md의 "페이즈 종료 절차" 2번 시나리오(POST→GET 폴링→워커 강제종료→stale 복구)도 같은 이유로 **실행하지 못했다.**
- `make migrate` 실제 실행 미검증 — 같은 이유(DB 없음). SQL 자체는 06-db.md 원문 그대로라 별도 위험은 낮다고 판단했다.
- `make dev`의 3개 프로세스 동시 기동 — `api`는 부팅과 라우트 노출을 직접 확인했다. `worker`는 DATABASE_URL 없이 즉시 예외(의도된 동작, jobs 테이블 자체가 Postgres 의존이라 fake 모드에서도 DB는 필요하다). `frontend`(`npm run dev`)는 **이 샌드박스의 inotify 워처 한도(fs.inotify.max_user_watches=65536, 컨테이너 전역 공유, sysctl 쓰기 금지)**에 막혀 부팅 자체가 안 됐다 — 같은 호스트에 떠 있는 다른 세션들이 워처를 이미 소모하고 있었다. 코드/설정 문제 아님. `npm run lint`/`npm run typecheck`는 정상 통과.

### 내가 내린 판단
- **pipeline/ 모듈명 ↔ JobStage 매핑**: CLAUDE.md는 모듈명을 `collect/score/frames/analyze/compare/guide`로, 계약 문서는 `JobStage`를 `collecting/scoring/downloading/analyzing/comparing/generating`으로 각각 정의하는데 둘을 잇는 표가 없었다. 위치 순서대로 1:1 매핑하고 `frames.py = downloading 단계(mp4 다운로드+ffmpeg 컷 추출+대표 프레임 추출)`, `analyze.py = analyzing 단계(VLM 호출)`로 판단했다 — 근거: 03-pipeline.md의 `analyzing` 절이 ffmpeg 컷 분해부터 VLM 호출까지 한 단계로 묶여 있어서, "프레임을 만드는 일"과 "프레임을 보고 서술하는 일"을 코드 모듈 단위로는 분리하는 게 재시작 단위(릴스별 커밋)와 맞고, `downloading` stage 이름과도 자연스럽게 맞아떨어진다.
- **`GET /api/health`의 `worker_alive` 판정**: DB 스키마에 워커 전용 heartbeat 테이블이 없다. `jobs.status='running'`인 잡들의 `MAX(heartbeat_at)`이 `STALE_MINUTES` 이내면 alive, **실행 중인 잡이 아예 없으면 판단 불가로 보고 `True`(죽었다고 단정하지 않음)**로 처리했다 — idle 워커를 dead로 오판하는 게 낫다고 봤다. 근거 약함, P1 이후 잡이 실제로 돌기 시작하면 재검토 필요.
- **Claude/Gemini 실제 provider의 구현 깊이 차등**: `ApifyCollectProvider`는 실제 HTTP 호출 코드까지 작성(P1 T-1.1에서 바로 써야 함), `ClaudeVisionProvider`/`ClaudeWriterProvider`/`GeminiVisionProvider`는 `NotImplementedError` 스텁만(P2/P4에서 구현 예정, 지금 만들면 프롬프트 없이 지어내게 된다). CLAUDE.md 완료조건 문구 "real 구현체는 P0에서 호출 코드만 있고 테스트하지 않는다"를 Apify에는 문자 그대로, Claude 계열에는 로드맵상 아직 프롬프트 로더(`prompts/`)조차 없어서 구현 자체를 유예했다.
- **DB 드라이버**: 명세에 없어서 임의 선택 — `psycopg[binary]` (v3, async). Celery/Redis 금지 외에는 스택 문서가 강제하지 않는 부분이라 표준적인 선택으로 판단.
- **`Job.result` 없이 `done` 처리 허용**: P0의 `guide.py` 파이프라인 모듈이 `pass`뿐이라 실제 `Guide`가 안 나온다. `jobs_db.mark_done(job_id, result=None)`을 허용해 "빈 파이프라인이 끝까지 돈다"를 성립시켰다 — 실제 `Guide` 생성은 P4 몫.

### 명세와 어긋났던 지점
- 없음. `docs/02-contracts.md` 스키마·필드명·Optional 여부는 전부 문서 그대로 이식했다.

### 다음 세션이 알아야 할 것
- **P1 시작 전 사용자가 로컬/테스트 Postgres(또는 Supabase 프로젝트) 하나를 마련해야 한다.** `DATABASE_URL`을 `.env`에 넣고 `make migrate` → `pytest`를 한 번 돌려서 T-0.3/T-0.4/T-0.6에서 스킵된 6개 테스트와 페이즈 종료 시나리오를 실제로 통과시켜야 G0가 완전히 닫힌다. 코드는 다 짜여 있어서 DB만 연결하면 바로 돌아갈 것으로 예상하지만, 실측 전이라 장담은 못 한다.
- `frontend`의 `npm run dev`는 이 세션에서 못 띄웠다(샌드박스 inotify 한도). 로컬 개발 머신에서는 문제없을 가능성이 높지만, 다음 세션도 같은 종류의 공유 샌드박스라면 같은 문제를 만날 수 있다.
- P1 T-1.1(실제 Apify 1회 호출)에 필요한 `APIFY_TOKEN`은 아직 없다. `ApifyCollectProvider`의 실제 정규화 로직은 그때 실물 응답을 보고 채운다(현재는 의도적으로 `NotImplementedError`).

---

## P0 — G0 재작업 (2026-08-06)

`tasks/g0-fixes.md` 지시서 A→B→C→D 반영. CLAUDE.md에 규칙 3-1 추가
(문서와 다르게 구현한 건 "임의 판단"이 아니라 "계약 충돌"이라는 규칙).

### 완료 — A (앞선 판단 재검토)
- **A-1 (계약 충돌 정정)**: `JobStage.downloading` → `preparing`으로 리네임. `docs/02-contracts.md`,
  `docs/01-architecture.md` 상태전이도, `docs/03-pipeline.md`(전 `downloading` 섹션을 `preparing`으로
  분리 — ffmpeg 컷 분해·프레임 추출만 여기 남기고, `analyzing`은 VLM 호출만 남김) 전부 갱신.
  코드: `schemas/common.py`, `pipeline/frames.py`, `worker/loop.py`.
  이전 세션에서 이걸 "임의 판단"으로 보고했는데, 실제로는 03-pipeline.md `analyzing` 섹션과
  다르게 구현하기로 한 것이었다 — 규칙 3-1 위반 사례였다.
- **A-2**: `workers` 테이블 신설(`0002_workers.sql`). 워커가 루프마다(잡 유무 무관) 자기 자신을
  upsert. `GET /api/health`의 `worker_alive`를 `jobs.heartbeat_at` 기반에서 `workers.last_seen_at`
  기반(최근 60초)으로 교체. `jobs_db.latest_running_heartbeat`/`is_worker_alive` 폐기,
  `app/db/workers.py` 신설. `docs/06-db.md`, `docs/05-api.md` 갱신.
- **A-3**: `docs/04-prompts.md` 원문을 `backend/prompts/vision_shot.md`, `guide_writer.md`로 그대로
  이식. `app/prompts.py` 로더 구현(`## System`/`## User` 섹션 파싱). `tests/test_prompts.py` 5개.
  Claude/Gemini provider는 기존대로 스텁 유지(프롬프트만 먼저 실물화).
- **A-4**: Supabase는 direct connection(5432)만 쓴다는 결정을 `.env.example`, `docs/06-db.md`에
  명문화. pooler(6543) 금지 이유(psycopg3 auto-prepare vs pgbouncer transaction 모드 충돌) 기록.

### 완료 — B (차단 결함)
- **B-1**: `tests/conftest.py`의 `TRUNCATE TABLE jobs` → `TRUNCATE TABLE jobs, workers CASCADE`
  (guides.job_id FK 때문에 CASCADE 없으면 거부당함).
- **B-2**: `process_job`이 `job.stage`를 보고 `STAGE_MODULES`에서 재개 인덱스를 찾아 그 단계부터
  실행하도록 수정(`_resume_index`). 전에는 매번 처음부터 돌았다. 이 과정에서 `STAGE_SEQUENCE`
  (함수를 미리 바인딩)를 `STAGE_MODULES`(모듈 객체를 담고 호출 시점에 `.run` 조회)로 바꿨다 —
  안 그러면 테스트에서 `patch("app.worker.loop.collect.run")`가 이미 바인딩된 참조를 못 바꾼다.
  테스트: `test_process_job_resumes_from_saved_stage` (앞 단계 mock이 호출 안 됐는지 확인).
- **B-3**: `process_job` 안에서 `asyncio.create_task`로 백그라운드 heartbeat 루프를 돌리고
  `finally`에서 취소. 기본 간격 30초, 테스트에선 인자로 짧게 오버라이드.
  테스트: `test_process_job_sends_background_heartbeat_during_long_stage`.
- **B-4**: `app/db/connection.py`를 매번 새 연결 여는 방식에서 `psycopg_pool.AsyncConnectionPool`
  (min=1, max=5)로 교체. FastAPI는 `lifespan`에서, 워커는 `__main__.py`에서 open/close.
  **주의**: 풀은 이벤트 루프에 종속돼서 테스트에서는 세션 스코프로 못 열어두고 테스트 함수마다
  `init_pool`/`close_pool`을 호출한다 (`tests/conftest.py`).
- **B-5**: `ScoredReel`에 model_validator 추가(불변식 2: `follower_count is None` →
  `reach_multiple`도 None이어야 함). `ReelAnalysis`에 model_validator 추가(불변식 3: `shots`가
  `t_start` 오름차순이어야 함). 실패 케이스 테스트 2개 추가, 전부 통과(23/23).

### 완료 — C (중요 결함)
- **C-1**: `JobDetailResponse.result: dict[str, Any]` → `Guide | None`, `status`/`stage`도
  `JobStatus`/`JobStage`로 강타입화. `CreateJobResponse.status`도 동일.
- **C-2**: `jobs.attempts` 컬럼 추가(`0003_job_attempts.sql`). `claim_next_queued_job`이 매번
  `attempts + 1`. `reap_stale_jobs`가 `(recovered, killed)` 튜플을 반환하도록 시그니처 변경 —
  `attempts < max_attempts(기본 3)`면 복구, 아니면 `failed` + `error='max attempts exceeded'`로
  영구 확정. 테스트 3개(증가 확인, 상한 미만 복구, 상한 도달 시 영구 실패).
- **C-3**: 자기 자신을 검증하던 실패 테스트를 `run_forever(iterations=2)`를 실제로 돌리는
  테스트로 교체. `run_forever`에 `iterations` 파라미터 추가(`None`=무한, 정수=그만큼만 — 테스트
  전용, 프로덕션 경로는 그대로 무한 루프). 지시서는 "poll_interval 짧게 + N사이클 후 취소"를
  제안했는데, 타이밍 기반 취소보다 결정론적인 `iterations` 카운터가 플레이키하지 않아서 이걸
  선택했다 — 검증하려는 것(예외 처리 후 다음 잡 계속 처리)은 동일하게 실제 `run_forever` 코드
  경로를 태운다.
- **C-4**: `WriterProvider.write_guide`에 `confidence: Confidence` 파라미터 추가(필수, 코드가
  계산해서 주입). `docs/03-pipeline.md` generating 섹션에 0번 스텝으로 명시.
  `FakeWriterProvider`는 fixture guide를 읽은 뒤 `confidence`만 덮어써서 반환.

### 완료 — D (경미)
- Settings를 클래스 속성 방식에서 `pydantic-settings BaseSettings`로 교체 — 이전엔
  `os.environ.get(...)`이 import 시점에 딱 한 번 평가돼서 `get_settings.cache_clear()`가
  아무 효과가 없었다(진짜 버그였다, 테스트에서 env override가 항상 무시되고 있었다).
- `fixtures_dir` 기본값을 `Path(__file__)` 기준 프로젝트 루트 절대경로로 변경. cwd에 안 흔들림.
- `cancel_analysis`: `assert cancelled is not None`(경합 시 500) → `None`이면 409로 응답.
- `AudioRecommendation`에 `seen_count <= total` model_validator 추가(FeatureCount와 동일 규칙).
- `run_forever`의 `mark_failed` 호출을 try로 감싸서, DB 일시 장애로 실패 기록 자체가 실패해도
  워커 루프가 죽지 않게 함.
- **덤으로 발견한 버그**: `Settings.model_config`의 `env_file=".env"`가 **상대경로**였다.
  `Makefile`이 항상 `cd backend &&`로 실행하기 때문에 실제로는 `backend/.env`를 찾고 있었는데,
  `.env`는 프로젝트 루트에 있다(CLAUDE.md 구조). 즉 **이 세션 전까지 `.env`가 한 번도 실제로
  로드된 적이 없었다** — DB 관련 테스트가 전부 "DATABASE_URL 없음"으로 스킵된 것도 이것 때문일
  가능성이 있었다. `Path(__file__)` 기준 절대경로(`프로젝트_루트/.env`)로 고쳤다. 이건
  g0-fixes.md에 없던 항목이지만 D 작업 중 발견해서 같이 고쳤다.

### 미완 / 보류 — E 검증 중단
**DATABASE_URL은 설정돼 있었다. 하지만 이 샌드박스에서 그 Supabase 프로젝트의 direct connection
호스트(`db.edgscvxkthjsesrrzpej.supabase.co:5432`)에 네트워크 계층에서 도달할 수가 없다.**

- `nslookup`/`getaddrinfo` 결과 이 호스트는 **AAAA(IPv6) 레코드만 있고 A(IPv4) 레코드가 없다**
  (Supabase는 IPv4 애드온을 안 사면 direct connection이 IPv6 전용이다).
- 이 샌드박스는 IPv6 아웃바운드 라우트가 없다(`Network is unreachable`, 실측 확인).
- `make migrate` 즉시 `OperationalError: Network is unreachable`로 실패.
- `pytest`는 `requires_db` 스킵 마커를 (D에서 발견한 버그를 고치고 나서) 제대로 통과해
  실제로 커넥션 풀을 여는데, 커넥션을 하나도 못 맺어서 `PoolTimeout: couldn't get a connection
  after 30.00 sec`로 전부 실패한다(스킵 아님 — 시도했다가 진짜로 실패하는 것). 11개 DB 테스트를
  전부 돌리면 테스트당 최대 30초씩 걸려서 총 5~10분이 걸리고 결과는 이미 알고 있어서(전부 같은
  원인), 첫 번째 실패만 실측하고 나머지는 돌리지 않았다.

**여기서 멈춘다.** 지시서 [2단계]의 "DATABASE_URL이 없으면 중단" 조건의 취지(= 실 DB로 검증
불가능한 상태)에 해당한다고 판단했다 — 값은 있지만 접속이 안 되는 것도 결과적으로 같다.
[3단계](G0 판정)~[6단계](P1 일부 구현·T-1.1·G1 보고)는 진행하지 않았다.

**pooler(6543)로 우회하지 않은 이유**: A-4에서 "pooler 금지, direct만 사용"을 이미 확정했다.
pooler는 IPv4로 붙을 가능성이 높고 `prepare_threshold=None`으로 psycopg3의 자동 prepare를 꺼서
회피할 수도 있어 보이지만, 이건 이미 승인된 연결 전략을 코드가 임의로 뒤집는 것이라 규칙 3-1
대상이다. 확인도 안 된 상태에서 혼자 바꾸지 않았다.

### 사용자가 결정해줘야 할 것
1. Supabase 프로젝트에 **IPv4 애드온을 구매**해서 direct connection에 IPv4 주소를 붙이거나,
2. **pooler(6543) + `prepare_threshold=None`** 조합을 예외적으로 승인하거나,
3. **IPv6 아웃바운드가 되는 환경**(사용자 로컬 머신 등)에서 `make migrate`/`pytest`/E 시나리오를
   대신 돌리거나.
   이 중 하나가 정해져야 E 검증(따라서 G0 최종 승인)을 진행할 수 있다.

### 다음 세션이 알아야 할 것
- 코드 쪽은 A~D 전부 반영 완료, `make check`는 **DB 없이 검증 가능한 범위**(ruff/mypy/pytest 중
  DB 비의존 28개/eslint/tsc)에서 전부 그린이다. DB 연결 문제만 풀리면 나머지 11개 테스트와
  `make migrate`, E의 5개 시나리오를 바로 이어서 돌릴 수 있는 상태다.
- `.env`의 `env_file` 경로 버그 때문에 이전 P0 보고서의 "DB 없음" 판단 일부는 부정확했을 수
  있다 — 실제로는 "DATABASE_URL이 있어도 안 읽고 있었다"였다. 코드는 이제 고쳐졌다.
- P1 T-1.1(Apify 실호출), G1 보고는 위 DB 접속 문제와 무관하게 `APIFY_TOKEN`이 아직 비어 있어서
  어차피 지금은 진행 불가.

---

## P0 — G0 최종 통과 (2026-08-07)

### A-4 재승인: Session pooler로 전환
사용자가 "direct connection은 이 환경에서 IPv6라 못 쓴다"를 확인하고 **Session pooler**
(`aws-*.pooler.supabase.com:5432`)로 전환을 승인했다. Transaction pooler(6543)는 여전히 금지
(워커가 커넥션을 오래 들고 있는 상시 프로세스라 트랜잭션 단위 pgbouncer 모드와 안 맞음).
Session pooler는 IPv4로 붙고 prepared statement도 지원해서 A-4 원래 의도(psycopg3 자동
prepare와 충돌 안 남)는 유지된다. `docs/06-db.md`, `.env.example` 갱신.

### 4단계: DB/외부 API 없이 가능한 순수 로직 구현
- `app/pipeline/collect.py`: `extract_hashtags`(해시태그 정규식), `filter_recent`(최근 30일),
  `is_relevant`(어절 3개 이하 전부 매칭/초과 75% 이상), `dedupe_by_caption_similarity`
  (`SequenceMatcher >= 0.82`). 순수 함수, `run()` 스텁은 그대로 둠(P1에서 Apify 연동과 같이 구현).
  **계약 갭 발견**: `docs/03-pipeline.md`는 관련성 매칭 대상에 "위치명"도 넣으라고 하는데
  `RawReel`(docs/02-contracts.md)엔 위치 필드가 없다. 필드를 지어내지 않고 캡션/해시태그/계정명
  3곳만 구현했다 — 위치 필드가 계약에 추가되면 그때 반영한다.
- `app/pipeline/score.py`: `calculate_metrics`(engagement_rate/share_rate/reach_multiple),
  `classify_bucket`(B1~B4/unknown, 하한 포함·상한 미포함으로 판단 — 경계 자체의 포함 여부가
  문서에 없어서 표준 구간 관례를 따름), `select_breakout`/`select_big_account`/`select_control`
  (follower_data_available=False 분기 포함).
  **의도적으로 안 정한 것**: "상위 N개"의 N은 문서 어디에도 숫자가 없다(ROADMAP도 "N개"로만
  표기). 숫자를 추측해서 하드코딩하는 대신 `top_n`을 함수 인자로 받게 설계했다 — 실제 개수는
  P1에서 수집량·팔로워 분포를 보고 정한다.
- 테스트: `tests/pipeline/test_collect_logic.py` 11개, `tests/pipeline/test_score_logic.py` 11개.
  전부 합성 객체로만 구성, `fixtures/`에는 손대지 않았다.

### E 검증 — 전부 통과
DATABASE_URL을 Session pooler로 교체 확인 후 진행.

- **`make migrate`**: 최초 실행 시 새 버그 발견 — `app/db/migrate.py`가 async connection에
  `conn.autocommit = True`(동기 API)를 써서 `AttributeError`. `await conn.set_autocommit(True)`로
  수정. 이후 정상 적용(`0001_init.sql`, `0002_workers.sql`, `0003_job_attempts.sql`), **재실행해도
  에러 없음(멱등성 확인)**.
- **`make check`**: ruff/mypy/eslint/tsc 전부 그린. **`pytest` 61개 전부 통과, 스킵 0개**
  (schemas 23 + prompts 5 + pipeline 22 + api/worker DB 테스트 11).
- **시나리오 1**: `POST /api/analyses` → `202 {"job_id":..., "status":"queued"}` 실측.
- **시나리오 2**: 실제 `python -m app.worker` 기동 후 `GET /api/analyses/{id}` 폴링 →
  `status: done` 확인.
- **시나리오 3**: 별도 스크립트로 `analyze` 단계에서 30초 슬립하게 만든 잡을 처리 중인 프로세스를
  `kill -9`. DB에 `status=running, stage=analyzing`으로 멈춘 것 확인 → `reap_stale_jobs` 호출 →
  `recovered=1`, `status=queued`로 복구되고 **`stage=analyzing` 유지** 확인.
  (실측 편의상 `stale_minutes=0`을 인자로 줬다 — 방금 죽은 잡이어도 "0분 초과"는 항상 참이라
  즉시 리퍼 대상이 된다. 운영 기본값 5분은 안 건드렸다.)
- **시나리오 4**: 복구된 잡을 다시 claim해서 처리 — `collect`/`score`/`frames.run`이 호출되면
  마커 파일을 쓰게 패치했는데 **마커가 하나도 안 생겼다** = 앞 단계들이 재실행되지 않고
  `analyzing`부터 재개됐다는 뜻. 최종 `status=done` 확인.
- **시나리오 5**: 워커를 한 번도 띄우지 않은 상태에서 `GET /api/health` → `worker_alive: false`
  확인 (예전 버그였다면 running 잡이 없다는 이유로 `true`가 나왔을 것). 워커를 띄우고 처리
  끝난 뒤 다시 조회하면 `worker_alive: true`로 바뀌는 것도 확인.

검증에 쓴 임시 스크립트(`/tmp/crash_worker.py`, `/tmp/resume_worker.py`)는 저장소 코드가 아니라
1회성 검증 도구라 실행 후 삭제했다. `jobs`/`workers` 테이블도 검증 후 비웠다.

### G0 자체 판정: **통과**
`make check` 스킵 0개로 전부 통과했고, phase-0.md가 요구한 5개 시나리오를 실제 DB로 전부
실행해서 확인했다. G0를 닫는다.

### 다음 세션이 알아야 할 것
- P1 진입 가능. 단 `APIFY_TOKEN`이 비어 있어서 T-1.1(실제 Apify 1회 호출)은 여전히 막혀 있다 —
  토큰이 생기면 그때 진행한다.
- 4단계에서 구현한 순수 로직(`app/pipeline/collect.py`, `score.py`)은 P1에서 실제 Apify 응답을
  박제한 뒤 `run()`에 배선한다. `select_breakout`/`select_big_account`/`select_control`의
  `top_n`은 그때 실측 수집량을 보고 정해야 한다 — 아직 미정.
- 위치명 매칭(`is_relevant`)은 `RawReel`에 위치 필드가 생기기 전까지는 캡션/해시태그/계정명만
  본다. 이후 계약에 위치 필드가 추가되면 `haystack` 구성에 추가해야 한다.

---

## P1 — 2026-08-14

### 완료
- T-1.1 **실제 Apify 1회 호출**: 액터 `apify/instagram-scraper`(id `shu8hvrXbJbY3Eb9W`)로
  `humansofny` 계정 릴스 100개 수집 → `fixtures/collect/dataset_instagram-scraper_*.json`.
  같은 액터의 `resultsType=details` 모드로 프로필(팔로워 수 포함) 조회 → `followersCount: 12644841`
  확인 → `fixtures/collect/profile_humansofny.json`.
- **G1 게이트**: 팔로워 필드 확보 가능 확인 → 사용자 결정 "프로필 액터 2차 호출 추가" →
  도달배수 축·돌파형/대형형 트랙 구분 로직 그대로 유지.
- T-1.2 **Provider 실구현 + accounts 30일 캐시**: `CollectProvider` 인터페이스를
  `collect_reels()`/`fetch_accounts()`로 분리. `ApifyCollectProvider`는 Apify API로 직접
  조회한 실제 input schema(`search`/`searchType`/`resultsType` enum) 기준으로 작성 —
  키워드는 해시태그로 검색(`resultsType=posts`, 최대 200건) 후 `type=="Video" and videoUrl
  존재`만 필터. `fetch_accounts()`는 `directUrls` 배치 + `resultsType=details` 한 번 호출.
  `app/db/accounts.py`(`get_cached`/`get_many`/`upsert_many`), `app/db/reels.py`
  (`upsert_many`/`get_by_keyword`) 신설.
- T-1.3/1.4/1.5 **관련성 필터·30일 필터·중복 제거 배선**: 기존 순수 함수(`is_relevant`,
  `filter_recent`, `dedupe_by_caption_similarity`)를 `pipeline/collect.py`의 `run()`에
  실제로 연결(이전엔 함수만 존재, 호출 안 됐음).
- T-1.6/1.7 **지표 계산 + 버킷 분류 + 트랙 선정**: `app/db/reel_metrics.py` 신설.
  `pipeline/score.py`의 `run()` 구현 — reels/accounts 재조회 → `ReelMetrics` 계산 →
  `reel_metrics` 테이블 커밋 → `follower_data_available` 판정 → breakout/big_account/
  control 트랙 선정(로그만, 저장 안 함 — 아래 "다음 세션이 알아야 할 것" 참조).
  `TRACK_TOP_N=20` 사용자 확정(comparing 단계 `n>=15` 가드에 여유).
- **collect.run()/score.run() 엔드투엔드 실측**: fake 모드로 job 생성 → collect → score
  실행, `reels`/`accounts`/`reel_metrics` 테이블에 실제 커밋되는 것 DB로 직접 확인
  (engagement_rate=0.08, reach_multiple=3.75, bucket=B2 등). 검증용 데이터는 실행 후 삭제.
- `ruff`/`mypy`/`pytest`(61개, 스킵 0) 전부 그린.

### 미완 / 보류
- **P1 수용 기준("돌파형 N개 + 대형형 N개 + 대조군") 완전 검증 안 됨** — 이유: `fixtures/
  collect/sample.json`(fake 모드용)에 릴스가 1개뿐이라 breakout=1, big_account=0,
  control=0으로 나옴. 메커니즘 자체는 맞게 동작하는 걸 확인했지만, 여러 버킷·트랙이
  실제로 갈리는 걸 보려면 fixture를 더 채우거나 실제 Apify 수집량(150~200건)으로 돌려야
  한다. `APIFY_MODE=real` 전환은 아직 안 함(비용 발생 + 대량 호출이라 사용자 확인 필요).
- **breakout/big_account/control 트랙 선정 결과 미저장**: 저장할 테이블이 스키마에 없음
  (의도적 — 아래 "내가 내린 판단" 참조). frames.py(P2)가 이 트랙 목록을 다시 만들어야
  다운로드 대상을 알 수 있는데, 그 재구성 코드는 아직 없다.
- **[2026-08-20 소급 기재]** `docs/02-contracts.md`의 "업종 누적 200건 초과 시 33/66
  분위수로 경계 교체" 기능이 이 시점엔 구현이 안 돼 있었는데, 완료 보고 당시 이 갭을
  명시하지 않았음(CLAUDE.md 규칙 4 위반) — 전체 계약 준수 감사(2026-08-20, P6 세션)로
  발견, 같은 날 구현 완료(`app/pipeline/score.py`의 `resolve_bucket_boundaries`,
  `app/db/bucket_configs.py`). 자세한 내용은 이 문서 하단 P6 섹션 참조.
- **[2026-08-24 소급 기재, 규칙 4 위반 2번째 사례]** T-1.1을 "완료"로 보고했지만,
  실제로는 **`fetch_accounts()`(프로필 조회, `directUrls`+`resultsType=details`)만
  실측했지 `collect_reels()`가 실제로 쓰는 해시태그 검색(`search`+`searchType=hashtag`)
  경로는 그때도, 그 이후로도 한 번도 실제 호출된 적이 없었다.** P6.5 세션(2026-08-24)에서
  처음 실제로 호출해보고서야 완전히 고장나 있다는 게 드러남(무관한 해시태그 메타데이터
  반환, 원본 수집 0건). 자세한 내용·수정 내역은 이 문서 하단 P6.5 섹션 참조.

### 내가 내린 판단
- **hashtags 필드는 Apify 원본이 아니라 캡션에서 정규식 재추출**: Apify 응답의 `hashtags`
  배열은 실측에서 항상 비어있었음(캡션에 실제 해시태그 텍스트가 없는 게시물이 많아서로
  추정). docs 03-pipeline collect 3번이 "캡션에서 정규식으로 추출"이라 명시하므로
  Apify의 원본 필드는 아예 무시하고 `extract_hashtags(caption)`만 신뢰했다.
- **is_video 판정**: Apify 응답엔 `is_video` 필드가 없다. `type=="Video" and videoUrl 존재`로
  대체 판정했다 — docs 계약 위반이 아니라 구현 매핑 선택(계약은 "is_video=True"라는 논리적
  조건만 요구, 필드명을 지정하지 않음).
- **트랙 선정 결과를 DB에 안 남김**: `reel_metrics`엔 `bucket`까지만 있고 `track` 컬럼이
  없다. `breakout`/`big_account`/`control`은 `top_n`+`bucket`+`reach_multiple`만 있으면
  언제든 순수 함수로 재계산 가능한 파생값이라, 새 테이블/컬럼을 만들기보다 다음 단계가
  필요할 때 재계산하는 쪽을 택했다 — 다만 이건 재검토 여지가 있다(P2에서 재계산 비용이
  크면 그때 저장 방식으로 바꿀 수 있음).

### 명세와 어긋났던 지점 (계약 충돌 — 규칙 3-1)
- **`reels` 테이블에 원본 참여지표 컬럼 없음**: `play_count`/`like_count`/`comment_count`/
  `share_count`가 `reel_metrics`에만 있고 `reels`엔 없었다. 워커가 단계 간 job_id로만
  통신하고 메모리 전달이 없어서, score 단계가 reels를 다시 읽으면 참여지표가 전부 0이 되는
  구조적 결함이었다. 사용자에게 보고 후 "reels에 4컬럼 추가"로 결정받음 →
  `backend/db/migrations/0004_reel_engagement_counts.sql` 작성, `docs/06-db.md` 갱신,
  `make migrate` 실행 완료.

### 다음 세션이 알아야 할 것
- **P2 진입 전 확인**: frames.py 작업 시작할 때 `score.py`의 `select_breakout`/
  `select_big_account`/`select_control`을 다시 호출해서 이번 job의 breakout/big_account/
  control 목록부터 복원해야 한다. 저장 안 돼 있다.
- `APIFY_TOKEN`/`ANTHROPIC_API_KEY`/`GEMINI_API_KEY` 상태는 이 세션 시작 시 확인한 그대로
  (Apify만 발급됨). Claude/Gemini 실 vision/writer provider는 여전히 스텁.
- Supabase 프로젝트가 무료 티어라 비활성 시 자동 pause된다(이번 세션에 실제로 겪음,
  ~1주 유휴 추정). 다음 세션에서 DB 테스트가 갑자기 다 실패하면 이것부터 의심하고
  대시보드에서 Resume 확인할 것.
- 프로젝트 절대경로가 바뀌었다: `/data/jyhan/han/personal/reels-analyzer`
  (구 경로 `.../2. 개인 프로젝트/창업프로젝트`는 더 이상 없음).

---

## P2 — 2026-08-14

### 완료
- T-2.1 ffmpeg scene detect(`select='gt(scene,X)',showinfo` 파싱) → `build_cut_boundaries`
  (경계 3개 미만이면 균등 5분할 폴백).
- T-2.2 컷 중앙 지점 대표 프레임 추출 + phash 해밍거리(임계값 5, 판단값) 중복 제거,
  최대 12장 상한.
- T-2.3 VLM 샷 서술: `ClaudeVisionProvider` 구현, `output_config.format`(structured
  outputs)으로 `VisionAnalysis` 스키마 강제. 샷 개수 불일치 시 1회 재시도.
- T-2.4 **G2**: Claude vs Gemini 실측 비교(합성 영상, 각 2~3회) — Claude가 안정성에서
  뚜렷이 앞섬(2/2 성공 vs Gemini 1/3 성공, 503 반복), Gemini가 ~2.3배 저렴하지만
  자막 위치 환각 1건 발견. **G2 확정: Claude 채택**, `.env` `VISION_MODE=real` 전환.
  `GeminiVisionProvider`는 폴백 후보로 코드에 남김.
- T-2.5 캐싱: `shot_segments.has_any(reel_code)`로 이미 처리된 릴스는 다운로드부터 스킵.
- T-2.6 mp4 즉시 삭제: analyzing이 VLM 호출 완료 후 프레임 폴더까지 삭제.
- 회고에서 발견한 명세 누락 처리: Apify 재시도(지수 백오프, 최대 4회 시도) 구현,
  fake vision fixture가 샷 1개 고정이라 컷 2개 이상인 릴스가 항상 스킵되던 문제 수정.
- 실제 Claude API로 합성 영상(4구간) 전체 파이프라인 실측 — 내용(테스트 패턴/프랙탈/
  노이즈) 정확히 서술 확인.
- `ruff`/`mypy` 그린, pytest 69→82개대까지 순차 통과.

### 미완 / 보류
- **frames.run()/analyze.run() 완전 자동화 테스트 없음** — 이유: 실제 mp4 다운로드
  (네트워크)와 VLM 호출이 필요해서 로컬 HTTP 서버·비디오 fixture 인프라 없이는 불가.
  이번 세션엔 수동 스크립트로 실측만 하고 삭제함.
- **엔드투엔드(collect→score→frames→analyze) 자동 테스트 없음** — collect→score만
  DB 테스트로 커버됨.
- Gemini 재비교(표본 확대)는 우선순위 낮음으로 보류(사용자 결정).

### 내가 내린 판단
- vision 모델 `claude-sonnet-5` 채택(G2), `effort="low"`(추출 작업이라 깊은 추론 불필요).
- `scene_detect_threshold=0.3`을 설정값으로 뺌(docs "임계값은 설정값으로" 요구사항).
- phash 해밍거리 임계값 5 — 문서에 숫자 없어 실측(구조 다른 프레임 보존/의도적 중복
  제거 둘 다 확인)으로 정한 값.
- `_select_target_reels`를 frames.py에서 `score.py`의 공개 `select_target_reels()`로
  이동(analyze.py도 필요해짐, 중복 제거).

### 명세와 어긋났던 지점 (계약 충돌 — 규칙 3-1)
- `docs/03-pipeline.md` preparing "커밋: 없음"이 `shot_segments` 스키마(t_start/t_end
  NOT NULL, VLM 필드 nullable)와 모순 — frames가 t_start/t_end/idx만 먼저 INSERT,
  analyzing이 UPDATE하는 구조로 문서 정정(사용자 승인).
- `reels.video_url` 컬럼 없음 → frames가 다운로드할 주소를 재조회할 수 없었음 →
  `0005_reel_video_url.sql` 추가(사용자 승인).

### 다음 세션이 알아야 할 것
- `ANTHROPIC_API_KEY`/`GEMINI_API_KEY` 둘 다 발급 완료, `.env`에 저장됨.
  `VISION_MODE=real`로 전환돼 있음(비용 발생 가능하니 테스트 작성 시 주의).
- `/tmp/buja_frames/{job_id}/{reel_code}/frame_{idx:02d}.jpg` 경로 관례 — frames.py가
  쓰고 analyze.py가 같은 경로로 읽은 뒤 삭제한다.

---

## P3 — 2026-08-14 (대조 분석)

### 완료
- `compute_feature_findings`(angle/movement/purpose는 샷 단위, subtitle_position/
  color_tone은 릴스 단위로 분모 분리, gap_pp>=30만 포함), `compute_timing_stats`,
  `build_comparison_result`(n>=15 가드, 계약 불변식 5 강제).
- `score.py`에 `compute_tracks()` 공개 분리(compare.py도 필요해짐).
- `compare.compute_comparison(keyword, business_type)`: reel_analyses+shot_segments
  조인해서 `ReelAnalysis` 재구성 → 매번 재계산(저장 안 함, 아래 "판단" 참조).
- 테스트 6개(순수 함수: n가드/gap_pp 임계값/timing 평균/빈 그룹) + DB 통합 테스트 1개.
  ruff/mypy 그린, pytest 82개 전부 통과.

### 미완 / 보류
- 없음 — P3 범위(같은 버킷 내 비교 + n 가드)는 온전히 구현·검증됨.

### 내가 내린 판단
- `score.select_breakout/control`이 B1+B2를 하나로 묶어 다루는데(docs score 5번)
  `ComparisonResult.bucket`은 단일값 — 사용자 결정: 비교 로직은 단일 비교로 유지,
  `bucket` 필드엔 breakout 풀에 실제 존재하는 가장 작은 버킷을 대표값으로
  (`_representative_bucket()`, 표시용일 뿐 통계엔 영향 없음).
- `ComparisonResult`를 담을 테이블을 스키마에 안 만듦 — docs comparing 절엔 "커밋"
  항목 자체가 없어서(문서 오류가 아니라 원래 그렇게 설계된 것으로 확인) reel_analyses+
  shot_segments만 있으면 결정론적으로 재계산 가능하다는 점을 근거로 매번 재계산 채택.

### 명세와 어긋났던 지점
- 없음.

### 다음 세션이 알아야 할 것
- guide.py(P4)도 `compare.compute_comparison()`을 그대로 재사용하면 된다 — 별도 조회
  경로를 새로 만들 필요 없음.

### [2026-08-20 소급] G3 게이트 승인
전체 계약 준수 감사(P6 세션)에서 G3(차이 문장 품질) 승인 기록이 이 문서에 없다는 걸
발견 — n>=15 가드(`MIN_GROUP_N`)와 gap_pp>=30 임계값(`MIN_GAP_PP`)이 `compare.py`에
그대로 강제돼 있고 `tests/pipeline/test_compare_logic.py`(6개: n가드 통과/미달, gap_pp
경계 포함/제외, timing 평균, 빈 그룹)로 검증돼 있는 걸 재확인 후 사용자가 소급 승인함.
**G3 승인.**

---

## P4 — 2026-08-14 (가이드 생성)

### 완료
- `compute_confidence`(docs 02-contracts 판정표: sufficient+findings>=2→충분,
  findings<=1→제한적, insufficient→불충분).
- `filter_reference_shots`(혼자 촬영→solo_alternative 치환/제외, 얼굴 노출 불가→
  "얼굴" 포함 subject 제외, 미보유 장비 요구 샷 제외).
- `render_user_prompt` + `prompts/guide_writer.md` 로더 연동, 개발자용 화살표 주석(`←`)과
  `{my_reel_block}`(당시 미구현) 제거 처리.
- `ClaudeWriterProvider`: structured outputs로 `Guide` 스키마 강제, 검증 실패 시 1회
  재시도, `confidence`는 항상 코드값으로 덮어씀.
- `app/db/guides.py` 신설(`create`/`get_latest_by_job`).
- **워커 버그 수정**: `worker/loop.py`가 `mark_done(job.id)`을 무인자 호출해서
  `jobs.result`가 영원히 None이었음(P0~P3는 guide.py가 스텁이라 안 드러났음) —
  `guides_db.get_latest_by_job()`로 방금 커밋한 Guide를 읽어 전달하도록 수정.
  사용자 피드백 없이 자율 발견·수정(내부 버그).
- **G4**: 실제 Claude API로 가이드 생성 실측 — solo_alternative 치환/얼굴 노출 조건
  정확히 반영 확인. `evidence_note`에서 퍼센트만 쓰고 원시 개수 병기 안 한 문장 발견
  (CLAUDE.md 금지 목록 위반) → `prompts/guide_writer.md`+`docs/04-prompts.md`(동기화)
  system 프롬프트에 evidence_note 전용 규칙 명시 추가 → 재검증(재생성)으로 해결 확인.
  **G4 승인.**
- 테스트 12개(confidence/필터링/프롬프트 렌더링/week_of) + DB 통합 테스트. ruff/mypy
  그린, pytest 95개 전부 통과.

### 미완 / 보류
- 없음.

### 내가 내린 판단
- `WriterProvider.write_guide()`가 원래 `pool: ReelPool`을 받게 돼 있었으나
  `ReelPool.collected_count` 등 어디에도 저장 안 되는 집계 필드라(P1부터의 기존 갭)
  프롬프트가 실제 쓰는 breakout/big_account `ReelAnalysis`만 받게 인터페이스를 좁힘
  — 순수 내부 인터페이스 변경, 출력 품질 영향 없어 사용자 확인 없이 처리.
- `_week_of`: ISO 주 시작(월요일) 관례 — 문서에 정의 없음.

### 명세와 어긋났던 지점
- 없음(evidence_note 건은 프롬프트 품질 이슈이지 스키마/코드 계약 위반은 아니었음,
  프롬프트 보강으로 해결).

### 다음 세션이 알아야 할 것
- P5(내 릴스 진단)로 진행.

---

## P5 — 2026-08-18 (내 릴스 진단)

### 완료
- ROADMAP엔 "목표만"으로만 적혀 있고 `docs/03-pipeline.md`엔 진단 단계 자체가 없어서
  설계안을 만들어 사용자 승인부터 받음(4가지 결정 — 아래 "판단" 참조).
- `reels.is_my_reel BOOLEAN DEFAULT false` 추가(`0006_reel_is_my_reel.sql`),
  `get_by_keyword()`가 항상 제외하도록 수정, `get_my_reel(keyword, business_type)` 신규.
- `CollectProvider.fetch_reel_by_url(url)` 추가. **실측(2026-08-18)**: Apify에
  `directUrls=[단일 포스트 URL]` + `resultsType=posts`로 조회하면 해시태그 검색과
  완전히 동일한 아이템 구조가 나옴 — `collect_reels()`와 파싱 헬퍼 공유.
- 새 `JobStage "diagnosing"` 추가(comparing과 generating 사이). `app/pipeline/
  diagnose.py` 신설: my_reel_url 없으면 즉시 스킵, 있으면 fetch → accounts/reels
  (is_my_reel=true) upsert → `frames.process_reel`/`analyze.process_reel` 재사용.
  실패해도 잡 전체를 안 막음.
- `frames.py`/`analyze.py`의 `_process_reel` → `process_reel`로 공개화(재사용 목적).
- `Track`에 `"my_reel"` 추가. `compare.py`에 `build_my_reel_analysis(reel_code,
  audio_title)` 신규(공용 `_build_reel_analysis` 헬퍼 위에 재구성, bucket="unknown").
- `guide.py`: `_my_reel_block_text(my_reel, comparison)` 신규(내 릴스 vs 돌파형 상위
  벤치마크 텍스트 렌더링, 벤치마크 없으면 명시), `render_user_prompt`/`run()`이 my_reel
  처리. `WriterProvider.write_guide()`에 `my_reel` 인자 추가(base/writer 양쪽).
  `prompts/guide_writer.md`+`docs/04-prompts.md`(동기화) my_reel_block 포맷 명세.
- fixtures/collect/sample.json에 `my_reel` 픽스처, `FakeCollectProvider.
  fetch_reel_by_url()` 신규.
- 테스트 10개 신규(provider 3, guide_logic 4, DB 3). ruff/mypy 그린, pytest 105개
  전부 통과.
- **실측 검증 (실제 Apify + Claude API 호출, 소액 과금)**: 실제 공개 릴스 URL로
  `diagnose.run()` 전체 경로 실행 — Apify 단일 URL fetch → `reels`(is_my_reel=true)
  커밋 → 실제 mp4 다운로드+ffmpeg scene detect(6컷) → Claude Vision 호출로
  shot_segments/reel_analyses 정상 커밋. 이어서 `compare.build_my_reel_analysis()` →
  `ClaudeWriterProvider.write_guide(..., my_reel=...)` 호출 — diagnosis 카드 3장
  (컷 수/평균 샷 길이/첫 컷 길이)이 코드가 계산한 실제 수치로 정확히 채워지고 gap_note도
  근거 있는 해석으로 생성됨 확인. 검증용 데이터 전부 정리함.

### 미완 / 보류
- **G5(UI 흐름·상태 표현) 미도달** — ROADMAP상 "P5 중반" 게이트인데 프론트엔드(P6)가
  아직 없어서 UI 흐름 자체를 판단할 수 없음. P6 착수 시점에 함께 판단해야 함.

### 내가 내린 판단
- `diagnosing` 스테이지를 `comparing` 다음·`generating` 직전에 배치 — 내 릴스 분석
  자체는 풀 비교와 순서상 독립이지만, generating이 벤치마크로 쓸
  `ComparisonResult.timing`이 먼저 있어야 하기 때문.
- 내 릴스를 `reels` 테이블에 함께 저장하되 `is_my_reel` 플래그로 격리하는 방식을
  채택(대안: 별도 테이블) — `shot_segments`/`reel_analyses`가 `reels(code)`를 FK로
  잡고 있어서 별도 테이블을 쓰면 FK 구조를 통째로 바꿔야 했음.

### 명세와 어긋났던 지점
- 없음 — ROADMAP이 P5를 "목표만"으로 남겨둔 것 자체가 신규 설계가 필요하다는 뜻이었고,
  설계안을 사용자 승인받고 진행했으므로 계약 충돌이 아니라 신규 설계.

### 다음 세션이 알아야 할 것
- P6(프론트엔드) 착수 시 `my_reel_url` 입력 필드가 `AnalysisRequest`에 필요함
  (이미 스키마엔 있음, `docs/05-api.md` 참조). G5는 P6 진행 중 UI 흐름이 잡히면 판단.
- diagnose.py의 실패 원칙은 "로그만 남기고 진단 없이 진행"이라 프론트엔드가 내 릴스
  URL이 잘못됐을 때 사용자에게 별도 안내를 줄지는 아직 미정 — `Guide.diagnosis == []`
  로 판단할 수밖에 없음(실패와 "애초에 URL 없음"을 API 응답만으로 구분 못 함, 필요하면
  이때 논의).

---

## P6 — 2026-08-20 (프론트엔드)

### 완료
- `docs/07-ui.md`(스켈레톤 문서, "P6 진입 시 G5에서 상세화") 기준으로 화면 3개 구현:
  입력(`InputPage`) → 진행(`JobPage`+`ProgressView`, 2초 폴링) → 결과(`JobPage`+
  `ResultView`, 탭 4개: 샷 리스트/자막/음원/진단). 디자인은 순수 Tailwind(컴포넌트
  키트 없음, 사용자 선택).
- `react-router-dom` 추가(`/`, `/jobs/:jobId` — job_id URL에 포함, 이탈 후 재방문
  가능. docs/07-ui.md 요구사항).
- `frontend/src/api/client.ts` 신규: 생성된 OpenAPI 타입 재노출 + `ApiError`로
  `{"detail":...}` 에러 통일 처리.
- 필수 상태 4종(로딩/에러/빈상태/표본부족) 전부 구현. confidence≠충분 시 caveat 강조
  표시(안 숨김).
- **백엔드 버그 발견·수정**: analyzing 단계 "7/20" 진행 표시용 `jobs_db.update_progress()`
  가 P0부터 있었는데 어느 파이프라인도 호출한 적이 없었음 — `analyze.py`의 `run()`에서
  릴스 처리마다 갱신하도록 수정, 테스트 추가.
- `docs/07-ui.md`에 diagnosing 단계 진행 표시 문구 보강(P5 스테이지가 스켈레톤 문서에
  반영 안 돼 있던 것).
- 실측: uvicorn+worker+vite 동시 기동, vite 프록시 경유로 실제 잡 생성→폴링→완료→404
  까지 curl로 확인. `npm run typecheck`/`lint`/`build` + `ruff`/`mypy`/`pytest` 전부
  그린.
- **전체 계약/체크리스트 준수 감사 실행**(포크로 독립 재검증) — 사용자가 "첫 의도대로
  준수했는지" 전체 확인 요청. CLAUDE.md 절대규칙/금지목록, docs 02~07, ROADMAP 게이트를
  실제 코드와 대조. **총평: 계약·원래 의도(분석 리포트 아님, 촬영 지시서) 충실히 지킴.**
  발견된 결함 5개 전부 처리:
  1. `react-router-dom` 승인 없이 추가(금지목록 위반) → 사용자 소급 승인.
  2. `bucket_configs` 33/66 분위수 교체(docs/02-contracts.md) 미구현+미완 기재 누락
     → 지금 구현(`app/db/bucket_configs.py`, `score.resolve_bucket_boundaries` 등,
     아래 "내가 내린 판단" 참조).
  3. G3 게이트 승인 기록 누락 → 기능 재확인 후 소급 승인(P3 섹션에 기록 추가).
  4. `docs/06-db.md` `jobs.stage` 컬럼 주석에 `diagnosing` 누락 → 수정.
  5. `test_run_forever_survives_stage_failure_and_claims_next_job` flaky 재현·원인
     재규명 → 아래 "명세와 어긋났던 지점" 참조.

### 미완 / 보류
- **P6 화면 시각 확인 안 됨** — SSH 원격 환경이라 로컬 브라우저 접근에 포트포워딩이
  필요한데 사용자가 번거로워서 스킵, 기능 레벨(API 응답 curl 검증)로만 G5 승인함.
  레이아웃·모바일 반응형 이슈는 실제로 열어봤을 때 발견되면 그때 고친다.

### 내가 내린 판단
- **`bucket_configs` 분위수 교체 해석(계약 3-1)**: "33/66 분위수"는 컷포인트가 2개뿐인데
  `bucket_configs.boundaries`는 B1/B2/B3 3개 키를 가짐 — B1·B2만 분위수(tertile)로
  교체하고 B3(메가 계정 절대 기준, 10만)는 고정 유지하기로 판단(문서가 이 매핑을
  명시하지 않음). `PERCENTILE_SWITCH_THRESHOLD=200`(문서 그대로), `PERCENTILE_MIN_
  SAMPLE=30`(분위수 계산에 필요한 최소 팔로워-데이터 샘플, 문서에 숫자 없어 판단).
  `score.run()`이 계산+저장, `compute_tracks()`는 읽기만(한 잡 안에서 scoring이 항상
  먼저 끝나므로 이후 단계는 그 값을 그대로 읽음 — 매 호출 재계산·재저장하면 이력
  테이블에 중복 row가 쌓임).
- **테스트 flaky의 진짜 원인 재규명**: 감사 포크는 "claim_next_queued_job의 ORDER BY
  타이브레이커 부재"를 원인으로 지목했으나, `id ASC` 타이브레이커 추가 후에도 100%
  재현되는 걸 확인하고 print 계측으로 재조사 — **진짜 원인은 다른 터미널(pts/97)에서
  살아있던 `make dev`의 실제 워커 프로세스가 같은 원격 Supabase DB를 폴링하며 pytest가
  만든 job을 가로채 처리한 것**(환경 오염, 코드 버그 아님). `make dev` 종료 후 동일
  테스트 3회 연속·전체 스위트 재실행 모두 통과 확인. id 타이브레이커 자체는 이론적으로
  옳은 강화라 유지. `CLAUDE.md`에 "make check 전엔 make dev를 꺼라" 경고 추가.
- pytest 106개(회귀 발견분 포함) → 최종 112개로 증가(bucket_configs 6개 + analyze
  progress 1개 + 기존 105개).

### 명세와 어긋났던 지점 (계약 충돌 — 규칙 3-1)
- 없음. 위 "내가 내린 판단"의 bucket_configs 33/66 해석은 문서가 매핑을 안 정해준
  부분을 채운 것이라 "충돌"이 아니라 "미정 사항 판단"으로 분류.

### 다음 세션이 알아야 할 것
- **P6 화면을 실제로 브라우저에서 열어본 적이 아직 없다** — 다음 세션에서 SSH 포트
  포워딩(`ssh -L 5173:localhost:5173 -L 8000:localhost:8000`)으로 한 번 확인 권장.
- **`make check`/pytest 전에는 항상 `make dev`가 안 떠 있는지 확인할 것** — 떠 있으면
  테스트가 비결정적으로 깨진다(이번에 실제로 겪음, `CLAUDE.md` 검증 섹션에도 경고 추가됨).
- 남은 페이즈는 P7(실키 전환·배포)뿐 — G6 게이트(실키 전환·배포, "비용 사고" 리스크)가
  걸려있어 진행 전 사용자 확인 필수.
- 남은 fixture 날짜 드리프트 이슈: `fixtures/collect/sample.json`의 `taken_at`이
  2026-08-12로 고정돼 있어 2026-09-11 근처부터 다시 30일 필터에 걸려 탈락함 —
  재발하면 원인 재조사 없이 바로 오늘 날짜 기준으로 당기면 됨.

---

## P6.5 — 2026-08-24 (실측, 1차 시도 — 무효)

> P7(배포) 진입 보류하고 사용자 지시로 실측 검증 먼저 진행. 목적은 코드 작성이 아니라
> 측정. **1차 시도는 실측으로 인정할 수 없어 무효 처리, 원인 규명 후 사용자 승인 대기
> 중(2번째 시도 전).**

### 완료 (인프라 준비)
- **G5 재개(부분)**: headless Chromium(Playwright, 프로젝트 의존성엔 안 넣고 `/tmp`
  스크래치에 설치) + 375px 뷰포트로 입력/진행/결과 3화면 실제 렌더링 확인.
  - 입력 화면: 필드·체크박스·장비 칩 375px에서 정상.
  - 진행 화면: 단계 7개 상태 전환(대기→진행중→완료) 시각적으로 정상 — 회색/검은 원/
    체크마크 확인.
  - 결과 화면: confidence 배지 + caveat(노란 박스+⚠) **명확히 눈에 띔**, 탭 전환 정상,
    "12개 중 4개" 원시개수 표기 확인, 진단 탭 조건부 숨김 정상.
  - **analyzing "N/M" 카운터는 이번에도 미확인** — fake 모드는 릴스 1개뿐이라 즉시
    스킵됨. 2차 실측(진짜 릴스 다수) 때 확인 필요(아래 "다음 세션이 알아야 할 것").
- **깔때기 로그 추가**: `collect.py` run()에 원본/30일필터/관련성필터/중복제거/계정조회
  (캐시히트·신규조회) 카운트 로그, `score.py` run()에 버킷분포+트랙별(breakout/
  big_account/control) 카운트 로그. `worker/loop.py`의 `process_job()`에 단계별
  소요시간 로그. `vision.py`/`writer.py`의 실제 Claude 호출에 input/output 토큰
  사용량 로그. 전부 관측용 추가라 스키마/동작 변경 없음.
- **요구사항 1(계정 조회 순서) 확인**: `collect.run()`은 이미 30일→관련성→중복 필터를
  전부 통과한 `deduped`에서 username을 뽑아 그 이후에만 `fetch_accounts()`를 호출하고
  있었음 — 코드 변경 불필요, 확인만 함.
- ruff/mypy/pytest(112개) 전부 그린 확인 후 실행.

### 발견 (실측 도중 — 중대)
1. **환경 오염: 좀비 `pytest` 프로세스 3개가 최소 6~10일째 백그라운드에서 살아있었음**
   (PID 272207/2996494/3161713, Aug14~Aug18에 시작된 이전 Bash 호출들이 타임아웃으로
   백그라운드 전환된 뒤 정리가 안 된 채 계속 실행 중이었음 — CPU 사용시간 116~198분
   누적). 이것들이 같은 원격 Supabase DB에 테스트 키워드("성수동카페"/"카페")로 데이터를
   계속 넣었다 지웠다 하면서 이번 실측 잡과 경합, `reels` 테이블에 낡은 fixture 행
   (`Cabc123`)을 다시 심어놓음 — **1차 실측 결과가 실제 Apify 데이터가 아니라 이
   오염된 fixture 1건을 기반으로 나온 것이었음**. 전부 `kill -9`로 정리, 관련 좀비
   `multiprocessing` 헬퍼 2개도 함께 정리. 이후 pytest 112개 재실행해서 깨끗한 상태
   확인.
2. **`collect_reels()`의 해시태그 검색이 실제로는 동작하지 않음(핵심 결함)**: 실제
   Apify 호출(`search="#성수동카페"`, `searchType="hashtag"`, `resultsType="posts"`)
   결과, 게시물이 아니라 **완전히 무관한 독일어 해시태그("potenzialentfaltung")의
   메타데이터 1건**이 돌아옴(`searchSource: "google"` — 퍼지 매칭으로 엉뚱한 해시태그에
   붙은 것으로 보임). `_item_to_raw_reel()`이 `type != "Video"`로 걸러내서
   **원본 수집 0건**. Apify 공식 문서(웹서치로 확인) 기준:
   - 현재 방식("search"+"searchType=hashtag")은 "해시태그 몇 개를 찾을지" 용도에
     가깝고, `search` 필드에는 원래 `#` **없이** 넣어야 함(현재 코드는 `#`을 붙여서
     보냄 — 이것도 원인의 일부일 수 있음).
   - 공식 문서가 "권장"하는 방법은 **`directUrls: ["https://www.instagram.com/
     explore/tags/{해시태그}/"]` + `resultsType: "posts"`** — 퍼지 매칭 없이
     결정론적으로 해당 해시태그의 게시물만 가져옴.
   - **이 해시태그 검색 경로는 P1 T-1.1 실측 때도 검증된 적이 없었다** — 그때 실측은
     `directUrls`로 특정 계정(humansofny) 프로필을 조회한 것이었지, 지금
     `collect_reels()`가 쓰는 해시태그 검색 자체는 이번이 첫 실제 호출이었음.
   - **코드는 고치지 않았다** — 사용자 지시("실패하면 그 자리에서 고치지 말고 보고")
     에 따라 원인만 규명하고 승인 대기.

### 실측 숫자 (1차 시도 — 무효, 참고용)
- 수집 원본: **0건** (필터 전 단계에서 이미 0)
- 30일/관련성/중복 통과: 전부 0건
- follower_data_available: N/A
- 버킷 분포: 오염된 fixture 1건 기준 B2=1 (실제 데이터 아님, 무의미)
- breakout/big_account/control: 1/0/0 (fixture 1건 기준, 무의미)
- ComparisonResult: sufficient=False, high_n=0, low_n=0, findings=0
- 최종 confidence: 불충분 (근거: fixture 1건 + 실제 evidence 0건)
- 단계별 소요시간: collecting 14.6s, scoring 1.8s, preparing 0.7s, analyzing 1.0s,
  comparing 0.7s, diagnosing 0.1s, generating 26.5s (총 ~46s)
- **실제 발생 비용**: Apify 해시태그 검색 호출 2회(실행 1회 + 원인규명 diagnostic
  1회, 각 1 result 과금 추정) ≈ $0.005, Claude Vision 호출 0회(분석 대상 자체가
  없어서 호출 안 됨), Claude Writer 1회(input 3337 / output 1642 토큰) ≈ $0.023.
  **총 약 $0.03(약 40원)** — 추정했던 $1.2~$2.2 대비 훨씬 적게 나감(원본 수집
  실패로 대부분의 파이프라인이 실행되지 않았기 때문).

### [3] 판정 — 이번 시도 기준으로는 판정 불가
- breakout/big_account/control이 실제로 갈렸는지: **판단 불가** — 실제 데이터가
  0건이라 트랙 분화 자체가 테스트되지 않음.
- n>=15 가드 통과 여부: 통과 못함(0/0) — 그러나 이건 진짜 병목이 아니라 원본 수집이
  아예 안 된 것이 원인. 진짜 병목(30일 필터인지 관련성 필터인지 등)은 원본 수집이
  정상화된 뒤에야 알 수 있음.
- 가이드가 "내일 이렇게 찍으세요"로 읽히는가: 이번 산출물은 evidence 0건 상태의
  일반 템플릿(caveat에 스스로 "실제 데이터 분석이 아닌 일반 템플릿"이라고 명시함)이라
  **품질 평가 대상 자체가 아님**. 정직한 평가는 원본 수집이 정상화된 2차 시도에서
  해야 함.

### 다음 세션이 알아야 할 것
- **`collect_reels()`의 Apify 호출 방식을 `directUrls`(explore/tags) 기반으로
  바꿀지 사용자 승인 대기 중.** 승인 나면 코드 수정 → 2차 실측 재시도.
- **환경 위생 수칙 추가 필요**: 긴 Bash 명령이 타임아웃으로 백그라운드 전환되면
  반드시 나중에 `ps aux`로 확인하고 정리할 것 — 이번에 6~10일간 방치된 좀비
  프로세스가 실측 결과를 오염시켰다. `make check`/실측 전에는 `ps aux | grep
  -E "pytest|app.worker|uvicorn|vite"`로 항상 사전 확인 습관화.
- G5의 analyzing "N/M" 카운터 확인은 2차 실측(원본 수집 정상화 이후) 때 반드시
  같이 확인할 것 — Playwright 감시 스크립트(`/tmp/.../scratchpad/pw/watch_analyzing.js`,
  세션 스크래치라 다음 세션엔 없을 수 있음, 필요하면 재작성)로 이미 준비돼 있었음.
- 관측용 로그 추가(`collect.py`/`score.py`/`worker/loop.py`/`vision.py`/`writer.py`)는
  그대로 유지 — 2차 실측에도 재사용됨.

### [A] 미검증 경로 전수 점검 (포크로 독립 조사, 2026-08-24)
사용자 지시로 "완료로 기록됐지만 실측 안 된" 외부 통신/파일 조작 경로를 전수 조사함.

| 경로 | 분류 | 근거 |
|---|---|---|
| `CollectProvider.collect_reels()`(해시태그 검색) | **미검증→방금 실측, 고장 확인** | P1 T-1.1 완료보고는 프로필 조회(`fetch_accounts`)만 실측, 해시태그 검색은 2026-08-24가 첫 실제 호출 |
| `CollectProvider.fetch_accounts()` | 실측함 | P1(2026-08-14), humansofny 프로필 `followersCount` 확인 |
| `CollectProvider.fetch_reel_by_url()` | 실측함 | P5(2026-08-18), 실제 릴스 URL로 단일 포스트 조회 구조 확인 |
| `ApifyCollectProvider._run()` 재시도(지수백오프) | 합성 데이터로만 검증 | `tests/providers/test_collect_provider.py` httpx mock 2개. 실제 Apify 장애 상황 미검증 |
| `frames.process_reel()`(다운로드+scene detect) | **실측함** | P5, diagnose.py가 실제 릴스(DZLK2U_M435)로 이 함수 재사용, 실제 다운로드+scene detect(6컷) 확인 |
| `frames.run()`(다중 릴스 순회+실패 격리) | 합성 데이터로만 검증 | P2에서 합성 mp4 1개로만 전체 경로 실행. 실제 릴스 여러 개를 동시 처리해본 적 없음 |
| `accounts` 30일 캐시 히트 | 합성 데이터로만 검증 | `test_accounts_upsert_and_cache`가 합성 타임스탬프로만 판정 로직 확인. `collect.run()`이 실제 운영에서 끝까지 성공한 적이 없어 실제 캐시히트 관측 자체가 없음 |
| `reap_stale_jobs()` max_attempts 영구실패 | 합성/DB 테스트로만 검증 | P0 G0에서 워커 1회 강제종료→복구는 실측했으나, `max_attempts`(3회) 도달 영구실패는 DB 테스트로만 확인. 실제 워커 3연속 사망 시나리오 미검증 |
| `GeminiVisionProvider` | 실측했으나 합성 데이터 기준 | G2(2026-08-14) 실측 전부 합성 영상 프레임(컬러바/프랙탈/노이즈). 실제 릴스 프레임으로는 미검증(Claude는 P5에서 실제 릴스로 검증됨) |
| `bucket_configs` 분위수 전환(`resolve_bucket_boundaries`) | 합성/DB 테스트로만 검증 | 오늘 새로 구현, DB 테스트로만 확인. 실제 200건 초과 데이터로 미검증(collect가 한 번도 200건을 모은 적이 없어서) |
| `update_progress()` N/M 카운터 | 합성/mock 테스트로만 검증 | P6에서 발견·수정한 버그, 단위 mock 테스트만. 실제 다건 분석 중 화면 증가 미확인 — [D]에서 확인 예정 |
| DB 커넥션 풀 재시도/재연결 | 해당 없음 | 별도 재시도 로직 자체가 없음(단순 `AsyncConnectionPool`), 매 실제 DB 호출마다 상시 실측되는 구조라 "미검증 갭" 범주가 아님 |

**결론**: `collect.run()`이 실제 운영 흐름에서 처음부터 끝까지 성공한 적이 지금까지
**한 번도 없었다** — 그 여파로 accounts 캐시 실사용/`frames.run()` 다중 릴스 루프/
`bucket_configs` 200건 전환까지 줄줄이 "합성으로만 검증" 상태로 남아있었던 구조적
문제. `collect_reels()`를 고치고 실제로 150~200건을 모으는 데 성공하면 이 목록의
절반 이상이 자동으로 실측 상태로 넘어갈 수 있음.

### [B] `collect_reels()` 수정
`search`+`searchType=hashtag` → `directUrls: ["https://www.instagram.com/explore/tags/
{태그}/"]` + `resultsType=posts`로 교체(`app/providers/collect.py`). `#` 제거,
`urllib.parse.quote()`로 한글 태그 퍼센트인코딩. `fetch_reel_by_url()`이 이미 쓰던
`_item_to_raw_reel()` 파싱 헬퍼 그대로 재사용(P5에서 이미 실측된 경로라 추가 검증
불필요, 확인만 함).

### [C] 최소 비용 사전 검증
`resultsLimit=8`로 실제 호출 — **의도치 않게 2회 호출됨**(1회 지시받았는데 첫 시도가
파싱 후 0건으로 나와서 원인 확인차 raw httpx로 1회 더 호출, 도합 16 results ≈ $0.043).
- ✅ 실제 게시물 옴(무관한 메타데이터 아님) — "#성수동카페" 캡션 실제 확인, directUrls
  전환 효과 확인됨.
- ❌ 8건 전부 "Sidecar"(사진), Video 타입 0건 — RawReel의 Video 매핑 자체는 이 회차로
  실증 못함, [D]에서 확인 필요.
- ✅ taken_at/username 필드 정상.
- ⚠️ **새 발견**: `likesCount`가 비공개 계정에서 **-1**로 옴(8건 중 6건). 기존 코드
  (`item.get("likesCount") or 0`)는 이걸 그대로 -1로 통과시킴 → [C-fix]로 처리(아래).

### [C-fix] `like_count` 계약 변경 (사용자 승인, 1~3번)
- **계약**: `RawReel.like_count`/`reels.like_count`/`reel_metrics.like_count`를
  `int` → `int | None`로 변경(`docs/02-contracts.md`, `docs/06-db.md`,
  `backend/app/schemas/collect.py`). `0007_reel_like_count_nullable.sql` 마이그레이션
  (두 테이블 모두 `DROP NOT NULL`+`DROP DEFAULT`). `Account.follower_count`와 동일한
  "None=모른다" 패턴.
- **파싱**: `_item_to_raw_reel()`에서 `likesCount < 0`이면 `None`으로 정규화(0으로
  안 채움).
- **engagement_rate**: `like_count`가 None이면 분자에서 빼고 계산(아는 값만) —
  0으로 지어내지 않음(`calculate_metrics()`).
- **편향 방지**: `select_control()`에서만(`follower_data_available=False` 분기)
  `like_count is None`인 릴스를 후보 풀에서 제외 — 비대칭 판단: breakout 쪽은
  과소평가라 무해(놓치는 실수), control 쪽은 인위적으로 저성과로 몰리는 유해한
  쏠림이라 여기만 가드. `reach_multiple` 분기(팔로워 데이터 있을 때)는 좋아요와
  무관해 영향 없음.
- **부가 확인(추가 API 호출 없이, Apify 공식 문서로 확인)**: `share_count`/`save_count`
  는 액터가 애초에 안 줌(매핑 누락 아님) — 공식 문서 샘플 스키마에 없음, 사진
  게시물 기준 우리 실측에서도 부재 확인(영상 기준은 [D]에서 확인). `docs/02-
  contracts.md`의 "share가 저장수 역할을 대신한다" 주석이 틀렸던 것으로 확인, 주석
  정정함 — **계산에는 영향 없음**(항상 0을 더하는 것뿐이라 왜곡 없음), P7로 후속
  조치(주석 정확성 외 추가 작업 없음) 이월.
- 테스트 2개 추가(`test_calculate_metrics_like_count_none_excluded_not_zeroed`,
  `test_select_control_excludes_unknown_like_count_when_no_follower_data`). ruff/mypy/
  pytest 114개 전부 통과.

### [D] 본 실측 2차 시도
- **체크포인트 1(collect 직후, score 전에 멈춤)에서 정지**: 키워드 "성수동카페" /
  `directUrls`(explore/tags 그리드, `resultsType="posts"`) / **원본 27건 수집, Video
  타입 0건**. 30일/관련성/중복 필터·계정조회 전부 0(필터링할 Video 대상 자체가 없어서).
  실제 비용: Apify 27 results ≈ $0.073.
  `resultsLimit=200`을 요청했는데 27건만 온 이유는 원인 불명(문서로 확인 못함).
  **원인 진단**: "패턴 없음"이 아니라 "수집 방법이 틀림"으로 판단 — `apify/
  instagram-scraper`의 `resultsType="posts"`가 해시태그의 **일반 게시물 그리드**(사진
  위주)를 반환하는 것이었고, 공식 문서 확인 결과 `resultsType="reels"`라는 릴스
  전용 값이 따로 있었음(안 쓰고 있었음). 다음 시도는 `resultsType="reels"`로 전환.
  job `eef3be04-b2cf-4e16-8784-3f7525e82e97`는 `queued` 상태로 보류 중(재사용 또는
  정리는 원인 조사 후 결정).
- **반복된 패턴 기록**: P1에서 input schema enum을 실제 조회했음에도
  `resultsType='posts'`를 선택했고, 그 결과 릴스 수집 경로가 P6.5까지 한 번도
  작동하지 않았다.
- **최소 비용 검증(8건, $0.022)**: `resultsType="reels"`로 바꿔서 같은 directUrls로
  재시도 — **8/8 전부 Video+videoUrl, `_item_to_raw_reel()` 그대로 통과**. 원인
  확정: `resultsType="posts"`가 문제였다. 영상 게시물에서도 공유수/저장수 필드
  부재 재확인(사진과 동일, [C-fix] 결론 그대로). `videoViewCount`는 전부 None,
  `videoPlayCount`만 채워짐(fallback 로직 정상). 음수 좋아요는 이번 샘플엔 없었음.
  resultsLimit=8 요청 시 8건 정확히 옴(27건 미달 문제는 이번엔 재현 안 됨, 200건
  스케일에서 재현되는지는 본 실측에서 확인). `resultsType="reels"`로 전환, 승인
  받아 코드 반영 완료.

### [D] 재실행 승인 후 사고 및 구조적 재발 방지
- **사고**: `[D]` 준비 중 `.env`를 real로 바꿔놓은 채 `ruff && mypy && pytest`를
  한 번에 돌림 — `test_loop.py`/`test_pipeline_db.py`의 거의 모든 fixture가
  keyword="성수동카페"를 쓰는데, 워커 전체 파이프라인을 실제로 구동하는
  `test_loop.py`의 테스트들이 **실제 Apify를 8회 이상 호출**해버림(30/1/30/1/1/30/
  30/30 = 153 results). 오늘 지출 총 재계산: Apify 214건($0.578) + Claude Writer
  1회($0.023) ≈ **$0.60**([C]가 "2회 호출"이라 보고했던 것도 실제로는 3회였음,
  정정). `.env` fake로 되돌리고 실패했던 2개 테스트 재실행 → 5.88초에 정상 통과
  확인(코드 버그 아님, 순전히 환경 실수).
- **구조적 재발 방지**(사용자 지시, "앞으로 조심"으로는 안 됨):
  1. `tests/conftest.py`에 `pytest_configure` 훅 추가 — `APIFY_MODE`/`VISION_MODE`/
     `WRITER_MODE` 중 하나라도 `real`이면 테스트 수집 전에 `pytest.UsageError`로
     세션 자체를 즉시 실패시킴. 실측 스크립트는 pytest를 안 타므로 영향 없음.
  2. **`VISION_MODE`도 가드 대상에 포함**(처음엔 "G2 이후 항상 real"이라 가드에서
     뺄지 논의했으나, 사용자가 반박: "fixture가 분석 대상을 안 만든다"는 보장은
     [D] 이후 무너진다 — 실측하면 실제 video_url 달린 릴스가 쌓이고 shot_segments
     캐시가 비면 테스트에서 진짜 Vision이 호출된다. 릴스당 $0.018로 셋 중 제일
     비싸 가드에 꼭 있어야 함). `.env`의 `VISION_MODE`도 `fake`로 내림 — 세 MODE
     전부 "평소엔 항상 fake" 관례로 통일.
  3. **`backend/scripts/real_mode.sh`(실측 진입점) 신설**: `.env`를 안 건드리고
     `env APIFY_MODE=real VISION_MODE=real WRITER_MODE=real <명령>`으로 그 프로세스
     (+자식 프로세스, `make dev`도 포함)에만 real을 준다. 프로세스별 환경변수라
     "복구" 단계 자체가 필요 없음(부모 셸/`.env`는 처음부터 안 바뀌었으므로) —
     `env`가 성공/예외 여부와 무관하게 그 프로세스 트리 밖으로 절대 안 새는 걸
     Unix 프로세스 모델로 실측 확인(`real_mode.sh` 안/밖에서 `get_settings()` 값
     비교).
  4. `docs/01-architecture.md`·`CLAUDE.md`에 "세 MODE는 항상 fake, 실측은
     `real_mode.sh`로만" 명문화.
  5. `pytest_configure` 가드 자체도 real_mode.sh로 감싸서 실제로 즉시 실패하는지
     실측 확인함, 평소 fake 상태에서 114개 정상 통과도 재확인.
