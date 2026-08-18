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
