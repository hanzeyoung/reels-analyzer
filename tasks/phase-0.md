# Phase 0 — 뼈대 · 계약 · 잡 시스템

> 이 페이즈의 목표는 **기능이 아니라 지반**이다.
> 여기서 계약이 흔들리면 P1~P7이 전부 흔들린다. 서두르지 마라.
> 종료 시 **G0** — 사용자 승인 필요.

---

## T-0.1 스캐폴드 + `make check`

**목표**: 빈 프로젝트가 lint/typecheck/test를 통과하는 상태

**건드릴 파일**: 루트 전체, `Makefile`, `pyproject.toml`, `frontend/package.json`

**완료 조건**
- [ ] `CLAUDE.md`의 디렉토리 구조와 실제 구조가 일치
- [ ] `make check` 실행 → 백엔드 ruff + mypy + pytest, 프론트 eslint + tsc 전부 그린
- [ ] `make dev` 실행 → api(8000) / worker / frontend(5173) 3개 동시 기동
- [ ] `.env.example` 존재, `.env`는 `.gitignore`에 포함
- [ ] 테스트가 0개여도 pytest가 exit 0

**주의**: 이 시점에 비즈니스 로직 코드를 쓰지 마라. 뼈대만.

---

## T-0.2 계약 스키마 코드화

**목표**: `docs/02-contracts.md`의 스키마를 Pydantic v2로 1:1 이식

**참조**: `docs/02-contracts.md` 전문

**건드릴 파일**: `backend/app/schemas/*.py`

**완료 조건**
- [ ] docs에 정의된 모든 모델이 존재하고, 필드명·타입·Optional 여부가 **문서와 완전히 일치**
- [ ] `Account.follower_count`가 `int | None`이다 (0 기본값 금지)
- [ ] 모든 모델에 `model_config = ConfigDict(extra="forbid")`
- [ ] `pytest tests/schemas/test_contracts.py` — 각 모델에 대해 유효 샘플 통과 + 잘못된 샘플 거부
- [ ] `make check` 그린

**멈춰야 할 때**: 문서 스키마에 모순·누락이 보이면 **코드로 메우지 말고 보고**하라. 그게 G0의 목적이다.

---

## T-0.3 DB 스키마

**목표**: DDL 작성 + 로컬/Supabase 양쪽 적용

**참조**: `docs/06-db.md`

**건드릴 파일**: `backend/db/migrations/0001_init.sql`, `backend/app/db/`

**완료 조건**
- [ ] 테이블 생성: `jobs`, `accounts`, `reels`, `reel_metrics`, `shot_segments`, `analyses`, `guides`, `bucket_configs`
- [ ] `jobs`에 `status`, `stage`, `progress_current`, `progress_total`, `heartbeat_at`, `error`, `created_at` 존재
- [ ] `reels`에 `code` UNIQUE (재수집 방지 키)
- [ ] `shot_segments`에 `(reel_id, t_start)` UNIQUE
- [ ] upsert에 쓰는 모든 `on_conflict` 대상 컬럼에 **실제 UNIQUE 제약이 걸려 있음**
- [ ] `make migrate` → `make migrate` 재실행해도 실패하지 않음(멱등)
- [ ] Pydantic 모델과 컬럼명 대조표를 `docs/06-db.md` 하단에 기록

**과거 실패 사례**: 이전 버전에서 `on_conflict="reel_id"`를 썼는데 UNIQUE 제약이 없어 런타임에 터졌다. 반드시 대조하라.

---

## T-0.4 잡 시스템

**목표**: 잡 생성 → 조회 → 진행률 갱신 → 죽은 잡 복구

**참조**: `docs/01-architecture.md` 상태 전이도, `docs/05-api.md`

**건드릴 파일**: `backend/app/api/routes/analyses.py`, `backend/app/db/jobs.py`

**완료 조건**
- [ ] `POST /api/analyses` → 202 + `{job_id}` 즉시 반환 (동기 작업 0)
- [ ] `GET /api/analyses/{id}` → `status`, `stage`, `progress`, `error` 반환
- [ ] 상태 전이가 문서와 일치: `queued → collecting → scoring → downloading → analyzing → comparing → generating → done` / `failed`
- [ ] 워커가 각 단계 진입 시 `stage` 갱신, 루프마다 `heartbeat_at` 갱신
- [ ] **stale 복구**: `heartbeat_at`이 N분(기본 5) 초과한 `running` 잡을 `queued`로 되돌리는 리퍼가 동작
- [ ] `pytest tests/api/test_jobs.py` — 생성/조회/진행률/stale 복구 4개 시나리오 통과

**stale 복구를 빠뜨리지 마라.** 워커가 죽으면 잡이 `analyzing`에서 영원히 멈춘다.

---

## T-0.5 Provider 인터페이스 + fake

**목표**: 모든 외부 의존을 인터페이스 뒤로 숨기고 fake 짝을 만든다

**건드릴 파일**: `backend/app/providers/`

**완료 조건**
- [ ] `CollectProvider`(Apify), `VisionProvider`(Claude/Gemini), `WriterProvider`(Claude) 3개 인터페이스 정의
- [ ] 각각 `real` / `fake` 구현 쌍 존재
- [ ] `APIFY_MODE` / `VISION_MODE` / `WRITER_MODE` 환경변수로 전환 (기본 `fake`)
- [ ] `VisionProvider`는 Claude 구현이 기본, Gemini는 **인터페이스만 있고 `NotImplementedError`**여도 됨
- [ ] fake 구현은 `fixtures/`에서 읽는다. **코드에 데이터를 하드코딩하지 마라**
- [ ] P0 시점 fixtures는 최소 골격만. 실물은 P1에서 박제한다
- [ ] `real` 구현체는 P0에서 호출 코드만 있고 테스트하지 않는다 (실 API 테스트 금지)

---

## T-0.6 워커 루프 골격

**목표**: 단계를 순회하는 빈 파이프라인이 끝까지 돈다

**건드릴 파일**: `backend/app/worker/`, `backend/app/pipeline/`

**완료 조건**
- [ ] `pipeline/` 하위에 `collect / score / frames / analyze / compare / guide` 6개 모듈, 각각 시그니처만 있고 `pass`
- [ ] 워커가 `queued` 잡을 집어 6단계를 순서대로 호출하고 `done`으로 종료
- [ ] 한 단계에서 예외 발생 시 → `failed` + `error` 기록 + **다음 잡으로 넘어감**(워커 프로세스가 죽지 않음)
- [ ] `make stage S=collect F=<name>` 으로 단일 단계만 독립 실행 가능
- [ ] `pytest tests/worker/test_loop.py` 통과

---

## 페이즈 종료 절차

1. `make check` 전체 그린 확인
2. 아래 시나리오를 **실제로 실행**하고 출력을 붙여서 보고:
   ```
   POST /api/analyses {"keyword":"성수동카페","business_type":"카페"}
   → GET /api/analyses/{id} 를 done 될 때까지 폴링
   → 워커를 강제 종료한 뒤 stale 복구가 동작하는지 확인
   ```
3. `tasks/PROGRESS.md` 작성
4. **G0 보고** — 아래를 명시:
   - 계약 스키마 중 문서와 어긋났거나 애매했던 지점
   - 내가 임의로 판단한 것과 그 근거
   - P1 진입 전 사용자가 결정해줘야 할 것

**승인 없이 P1로 넘어가지 마라.**
