# CLAUDE.md

## 프로젝트

**부자(Buja)** — 소상공인 인스타 릴스 **촬영 지시서 생성기**.

분석 리포트가 아니다. "내일 카메라 들고 몇 초에 뭘 어떻게 찍을지"를 출력하는 게 전부다.
점수·등급·차트는 목적이 아니라 **교재로 쓸 릴스를 고르는 필터**일 뿐이다.

산출물 4종:
1. 샷 리스트 (컷별 시각/구도/피사체/자막)
2. 자막 카피 초안
3. 음원 추천
4. 내 릴스 vs 상위 릴스 차이 진단

---

## 절대 규칙 (위반 시 작업 중단)

1. **계약이 진실이다.** `docs/02-contracts.md`의 스키마와 코드가 다르면 **코드가 틀린 것**이다.
2. **스키마·API·DB 변경이 필요하다고 판단되면 코드를 고치지 말고 멈춰라.**
   docs 수정 제안 → 사용자 승인 → 코드. 순서를 뒤집지 마라.
3. **명세에 없는 것을 추측해서 채우지 마라.** 애매하면 질문한다.
   질문 비용 < 재작업 비용. 이 프로젝트에서 추측은 실패의 1번 원인이다.
3-1. 문서에 명시된 것과 다르게 구현하기로 판단했다면, 그건 "임의 판단"이 아니라
     "계약 충돌"이다. 보고 시 어느 문서 어느 항목과 충돌하는지 반드시 명시한다.
4. **완료 조건을 전부 통과하지 못한 상태로 "완료"라고 보고하지 마라.**
   통과 못 한 항목은 통과 못 했다고 명시하고 이유를 써라.
5. **게이트에서는 반드시 멈춘다.** `tasks/ROADMAP.md`의 G0~G6.

---

## 스택 (고정. 변경 제안하지 마라)

| 영역 | 선택 |
|---|---|
| 백엔드 | FastAPI + Pydantic v2 |
| 잡 실행 | DB job 테이블 + 별도 워커 프로세스 + 폴링 (Celery/Redis 금지) |
| DB | Supabase (Postgres) |
| 프론트 | Vite + React + TypeScript + Tailwind + TanStack Query |
| 타입 공유 | OpenAPI → TS 자동생성 |
| 컷 경계 | ffmpeg scene detect (VLM 추정 금지) |
| 비전/생성 | Claude API 단일 (Gemini는 어댑터 자리만) |

---

## 디렉토리

```
buja/
├── CLAUDE.md
├── docs/              # 명세. 단일 진실원천
├── tasks/             # 페이즈별 지시서 + PROGRESS.md
├── fixtures/          # 실제 API 응답 박제본
├── backend/app/
│   ├── schemas/       # Pydantic = 계약
│   ├── api/routes/
│   ├── pipeline/      # collect/score/frames/analyze/compare/guide
│   ├── providers/     # apify, claude, gemini — 인터페이스 + fake 쌍
│   ├── worker/
│   └── db/
└── frontend/src/
    ├── api/generated/ # 자동생성. 손대지 마라
    ├── features/
    └── components/
```

---

## 검증

```bash
make check     # lint + typecheck + test. 이게 통과해야 완료다
make dev       # api + worker + frontend 동시 실행
make stage S=analyze F=cafe_20   # 단일 단계만 fixture로 실행
```

**주의**: 테스트가 별도 DB로 격리돼 있지 않고 실제 개발용 Supabase DB를 그대로 쓴다.
`make dev`(워커 포함)가 백그라운드에 살아있는 상태로 `make check`/pytest를 돌리면 워커가
테스트 job을 가로채 처리해버려 결과가 비결정적으로 깨진다(실제로 겪은 사례, 2026-08-20) —
`make check` 전에는 `make dev`를 꺼라.

**`make check`/실측 전 프로세스 사전 점검(필수)**: 아래 명령으로 남아있는 프로세스가
없는지 항상 먼저 확인해라.

```bash
ps aux | grep -E "pytest|app.worker|uvicorn|vite|node.*vite" | grep -v grep
```

- **좀비 `pytest` 프로세스도 `make dev`와 똑같은 문제를 일으킨다.** 타임아웃으로
  백그라운드 전환된 `pytest`/`python -m app.worker`/`uvicorn`/`npm run dev` 호출을
  안 죽이고 방치하면 며칠씩 살아남아 같은 원격 DB에 테스트 데이터를 계속 쓰고 지우며
  실측 결과를 오염시킨다(실제로 겪은 사례, 6~10일간 방치돼 실측 잡 하나를 완전히
  무효로 만듦, 2026-08-24). **긴 명령이 "타임아웃으로 백그라운드 전환됨" 알림을 받으면,
  그 작업이 끝난 뒤 반드시 위 `ps aux` 명령으로 확인하고 `kill -9`로 정리할 것** —
  "나중에 확인하면 되겠지"로 넘기지 마라.
- `nohup ... &`로 띄운 것도 마찬가지로 작업이 끝나면 명시적으로 죽여라. 죽였는지
  확인 없이 다음 작업(특히 실 API를 호출하는 실측)으로 넘어가지 마라.

**`APIFY_MODE`/`VISION_MODE`/`WRITER_MODE`는 항상 fake다. `.env`를 손으로 real로
고치지 마라.** `make dev`(운영)와 `pytest`(테스트)가 같은 `.env`를 공유해서, 손으로
바꿔놓고 되돌리는 걸 잊으면 테스트가 실제 API를 호출해버린다(실제로 겪은 사고,
$0.4 이상 의도치 않게 과금됨, P6.5 2026-08-24). 실측(real API로 직접 확인)이 필요하면
`backend/scripts/real_mode.sh <명령>`으로만 해라 — `.env`는 그대로 두고 그 명령의
프로세스(및 자식 프로세스)에만 real 환경변수를 준다. `tests/conftest.py`의
`pytest_configure`가 세 MODE 중 하나라도 real이면 `pytest` 세션 자체를 즉시
실패시키는 구조적 가드도 있다 — 이 가드가 막아준다고 안심하지 말고, 애초에 `.env`를
안 건드리는 습관을 지켜라.

---

## 금지 목록

- `frontend/src/api/generated/` 직접 편집
- 실 API를 호출하는 테스트 작성 (전부 fixture 기반)
- `requirements.txt` / `package.json`에 명세 없는 패키지 추가
- 프롬프트를 코드에 하드코딩 (전부 `docs/04-prompts.md` → `prompts/` 로더 경유)
- 영상 mp4를 분석 후 보관 (즉시 삭제. 파생 피처만 DB)
- 리포트에 퍼센트만 쓰기 (반드시 "18개 중 14개" 형태 병기)
- 그룹 n < 15인데 차이 문장 생성

---

## 데이터 원칙 (자주 틀리는 지점)

- `follower_count`는 **None 허용**이다. 없으면 반응률 단독 축으로 자동 전환. None을 0으로 채우지 마라.
- 수집은 **최근 30일**만. 오래된 릴스는 조회수가 누적된 것이지 잘 만든 게 아니다.
- 비교는 **같은 팔로워 버킷 안에서만**. 대형 계정 vs 소형 계정 비교는 촬영 기법이 아니라 예산 차이를 잡아낸다.
- 돌파형(소형 계정 고성과) → 샷 리스트·촬영팁에만 사용
- 대형형(대형 계정 고조회) → 음원·소재·해시태그에만 사용
- 컷 수·샷 길이는 ffmpeg에서. 구도·피사체·자막은 VLM에서. **섞지 마라.**

---

## 세션 운영

1. 한 세션 = 한 페이즈. 끝나면 `/clear`.
2. 페이즈 종료 시 `tasks/PROGRESS.md`에 기록:
   완료 태스크 / 미완 + 이유 / 내가 내린 판단과 근거 / 다음 세션이 알아야 할 것
3. 세션 시작 시 `CLAUDE.md` → `tasks/PROGRESS.md` → `tasks/SESSION_LOG.md` → 해당 `tasks/phase-N.md` 순으로 읽는다.
4. 페이즈 중간에 다음 페이즈 작업을 미리 하지 마라.
5. **세션 도중 수시 동기화**: 페이즈 종료를 기다리지 않고, 다음 일이 생기면 그때그때
   `tasks/SESSION_LOG.md`에 짧게 append한다 (형식 자유, 날짜만 구분):
   - 게이트(G0~G6) 판단에 쓸 실측 데이터/발견
   - 외부 리소스 확정 (액터 ID, 사용한 API, 토큰 발급 등)
   - 사용자가 세션 중간에 내린 결정
   - 다음에 이어서 할 일이 명확해진 시점
   페이즈가 끝나면 이 로그를 요약해서 `tasks/PROGRESS.md`로 옮기고 `SESSION_LOG.md`는 비운다
   (PROGRESS.md = 페이즈별 확정 기록, SESSION_LOG.md = 그 사이 임시 메모장).

---

## 사용자에 대해

- 한국어 반말로 답한다. 서론·사과·과잉 확인 생략.
- 코드보다 **판단 근거**를 먼저 말한다. "왜 이렇게 했는지"가 결과물보다 중요하다.
- 모르면 모른다고 한다. 그럴듯하게 지어내면 프로젝트가 망한다.
