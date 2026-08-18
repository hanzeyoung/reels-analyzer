# SESSION LOG

> 세션 도중 수시로 append하는 임시 메모장. 페이즈 종료 시 요약해서 `PROGRESS.md`로 옮기고 비운다.
> 형식 자유, 날짜만 구분해서 쓴다.

---

## 2026-08-14 (계속, P2 진입)

- **계약 갭 2개 더 발견, 둘 다 사용자 승인 받고 해결**:
  1. `reels.video_url` 없음 → frames.py가 mp4 다운로드 못 함. 컬럼 추가로 해결
     (`0005_reel_video_url.sql`).
  2. `docs/03-pipeline.md` preparing 단계 "커밋: 없음"이 `shot_segments` 스키마
     (t_start/t_end NOT NULL, VLM 필드 nullable) 및 스킵 로직 문구와 모순 —
     frames가 t_start/t_end/idx만 먼저 INSERT, analyzing이 UPDATE하는 구조로
     정정(문서 오류로 보고 수정).
- **의존성 추가**: Pillow, ImageHash (phash 중복 제거용, docs 명시 요구사항이라
  "명세 없는 패키지" 아님).
- **`app/config.py`**: `scene_detect_threshold: float = 0.3` 추가 (docs "임계값은
  설정값으로 뺀다" 요구사항).
- **`app/db/shot_segments.py`**(신설): `has_any()`(스킵 판정), `insert_cut_timings()`.
- **`app/pipeline/frames.py` 구현**:
  - `_parse_scene_change_times`: ffmpeg showinfo stderr에서 `pts_time:` 파싱
  - `build_cut_boundaries`: scene 경계로 구간 생성, 3개 미만이면 균등 5분할 폴백
  - `_ffprobe_duration`/`_run_scene_detect`/`_extract_representative_frames`: ffmpeg
    subprocess(asyncio) 래핑
  - `dedupe_by_phash`: imagehash.phash 해밍거리(임계값 5, 판단값) 기준 중복 제거 +
    최대 12장 상한
  - `_select_target_reels`: score.py의 select_breakout/big_account/control **재호출**로
    이번 job의 트랙 재구성 (P1에서 남긴 숙제 해결)
  - `run()`: 대상 릴스마다 shot_segments 존재 시 스킵 → 다운로드 → scene detect →
    프레임 추출 → phash dedup → shot_segments 커밋. 릴스 1개 실패는 로그만 남기고 계속.
  - **mp4/프레임 파일은 여기서 안 지움** — docs상 삭제는 analyzing 단계(VLM 호출 후) 몫.
    `/tmp/buja_frames/{job_id}/{reel_code}/`에 남아있음 — analyze.py 구현 시 반드시
    이 경로 관례를 알고 지울 것.
- **검증**:
  - `build_cut_boundaries`/`_parse_scene_change_times` 순수 함수 테스트 6개 작성
    (`tests/pipeline/test_frames_logic.py`).
  - **실측**: 로컬에서 ffmpeg로 구조가 다른 3~4구간 합성 영상 만들어서 scene detect
    (경계 정확히 잡음, life 필터 노이즈로 구간 하나 더 생기지만 무해) → 프레임 추출 →
    phash dedup(구조 다른 프레임 4개 다 보존, 의도적으로 섞은 중복 프레임은 정확히
    걸러짐) 확인. 단색 배경으로 처음 시도했을 때 phash가 색 구분을 못 해 전부
    "동일"로 오판했던 것 발견 — phash는 구조/텍스처 기반이라 색맹인 게 정상 동작,
    테스트 영상을 구조 다르게 다시 만들어서 재검증함(버그 아님).
  - 로컬 HTTP 서버로 합성 mp4 서빙 → `frames.run(job_id)` 전체 경로(다운로드 포함)
    엔드투엔드 실행 → `shot_segments`에 4개 행(t_start/t_end/idx, VLM필드 NULL) 실제
    커밋 확인. 검증용 서버/파일/DB행 전부 정리함.
  - `ruff`/`mypy`/`pytest`(67개, 스킵 0) 전부 그린.
- **ANTHROPIC_API_KEY 발급받음**, `.env`에 저장(채팅에 평문 노출됐던 키 — 나중에 콘솔에서
  폐기 권장).
- **T-2.3 구현 완료 (`analyze.py`, VLM 샷 서술)**:
  - `providers/vision.py`의 `ClaudeVisionProvider` 실구현. `claude-api` 스킬로 최신
    Vision API 사용법 확인 후 작성 — 모델은 `claude-sonnet-5`(judgment: 릴스마다
    반복되는 배치 작업이라 비용 누적, opus 대신 선택 — T-2.4 G2에서 재검토 대상).
    `output_config.format`(structured outputs, json_schema)으로 `VisionAnalysis`
    스키마 강제 → 파싱 실패 리스크 제거. `effort: "low"`(추출 작업이라 깊은 추론 불필요).
    이미지+텍스트 혼합 messages라 SDK 타입이 아직 못 따라와서 `output_config`/`messages`에
    `type: ignore` 필요(런타임엔 문제없음, anthropic 0.120.2 확인).
  - `app/db/shot_segments.py`: `get_pending()`(VLM 필드 NULL인 행만), `update_vlm_fields()`.
  - `app/db/reel_analyses.py`(신설): 릴스 단위 요약 upsert. 테이블에 track/bucket
    컬럼이 없어서(그 값은 reel_metrics.bucket + score.select_target_reels() 재계산으로만
    존재) `ReelAnalysis` 전체가 아니라 테이블이 실제 갖는 컬럼만 받게 설계.
  - `app/pipeline/analyze.py` 구현: score.select_target_reels() 재사용 →
    shot_segments.get_pending()로 미분석 릴스 판별 → 프레임 경로 재구성
    (`/tmp/buja_frames/{job_id}/{reel_code}/frame_{idx:02d}.jpg`, frames.py와 동일
    관례) → VLM 호출 → 샷 개수 불일치 시 1회 재시도(docs analyzing 2번) → shot_segments
    UPDATE + reel_analyses 커밋 → **mp4/프레임 폴더 삭제**(docs analyzing 4번 "mp4 즉시
    삭제"를 여기서 수행 — frames.py는 일부러 안 지웠음, 세션 로그에 이미 기록됨).
  - **리팩터링**: `_select_target_reels`가 frames.py에 private으로만 있었는데 analyze.py도
    필요해져서 `score.py`에 `select_target_reels()`로 공개 이동, `score.run()`도 이걸
    재사용하게 정리(중복 제거).
  - ruff/mypy 그린, pytest 67개 통과.
- **실측 검증 (실제 Claude API 호출, 소액 과금)**: 로컬 합성 영상(구조 다른 4구간)
  으로 `frames.run()` → `analyze.run()`(vision provider만 실제로 교체, `.env`의
  `VISION_MODE=fake` 전역 설정은 안 건드림) 전체 파이프라인 실행. **Claude Sonnet 5가
  합성 영상 내용(TV 테스트 패턴/프랙탈/노이즈)을 정확히 서술** — "TV 컬러바 테스트 화면",
  "프랙탈 패턴 화면", "랜덤 노이즈 패턴 화면"으로 구도·피사체 정확히 구분. `shot_segments`
  5개 행 UPDATE 확인, `reel_analyses` 요약 커밋 확인 (color_tone/summary 등 한국어로
  자연스럽게 생성됨). 검증용 데이터/mp4/http서버 전부 정리함.
- **GEMINI_API_KEY 발급받음**(Google AI Studio, `AQ.`로 시작하는 특이 포맷 — 실측으로
  유효함 확인, `AIzaSy...` 표준 포맷 아님에 주의). `.env`에 저장.
- **T-2.4 (G2 게이트) 진행 — Gemini 구현 + 실측 비교**:
  - `GeminiVisionProvider` 구현. `google-genai`(신 SDK) 추가.
  - **모델 가용성 실측**: `gemini-2.5-flash` 등 버전 고정 모델은 이 계정에서
    "no longer available to new users" 404. `/v1beta/models` 조회로 실제 사용 가능한
    모델 확인 — 별칭 `gemini-flash-latest`가 정상 동작. 계정별로 달라질 수 있는 값이라
    고정 버전 대신 별칭 채택.
  - **SDK 버그 발견 및 우회**: `response_schema`에 pydantic 모델(`VisionAnalysis`)을
    그대로 넘기면 `google-genai 2.18.1`이 `ConfigDict(extra="forbid")`가 만드는
    `additionalProperties`를 `additional_properties`로 잘못 변환해 Gemini API가
    400으로 거부함(`$defs`/`$ref`로 분리된 중첩 모델이 있을 때만 재현 — 단순 모델은
    문제없었음, 직접 실측으로 원인 특정함). 우회: `_gemini_schema()` 헬퍼로
    additionalProperties/title/$defs 제거 + $ref 인라인한 순수 dict를 넘기는 걸로
    해결(실측 확인). **이것도 스키마 준수율 비교의 실측 데이터임 — Claude는 이런 우회가
    전혀 필요 없었음.**
  - thinking_config(thinking_budget=0)로 Gemini도 비용 절감(Claude effort="low"와
    같은 취지).
  - **실측 비교 결과** (합성 영상 3구간, 동일 프레임/프롬프트로 Claude vs Gemini 동시 호출):
    - Claude Sonnet 5: 2회 호출 전부 성공(6.9s, 8.1s), 스키마 그대로 통과, 서술 정확
      (컬러바/프랙탈/노이즈 정확히 구분).
    - Gemini(gemini-flash-latest): **3회 중 2회 503(서버 과부하)로 실패**, 성공한
      1회는 5.0s로 빠름 — 근데 실제로 없는 자막을 "중앙"에 있다고 잘못 판단함
      (subtitle_position 오검출). 컬러바 화면의 숫자는 잘 읽었음("숫자 2").
    - **샘플 수가 작아서(각 2~3회) 통계적 결론은 아니고 방향성 정도**: Claude가
      안정성(성공률)에서 뚜렷이 앞섬, Gemini는 빠르지만 이번 표본에서 불안정했고
      환각(hallucination) 한 건 발견. 스키마 준수는 우회 코드 없이 되는 Claude가
      더 매끄러움(Gemini는 SDK 버그 우회가 필요했음).
  - **G2 최종 판정 보류**: 표본이 너무 작음(실측 2~3회씩). 확정하려면 실제 릴스
    프레임으로 최소 10~20건씩 돌려서 성공률/OCR 정확도/비용을 통계적으로 비교해야
    함 — 지금은 "Claude가 1차 후보, Gemini는 폴백 후보" 정도의 잠정 판단.
- **G2 확정: Claude 채택**. `.env`의 `VISION_MODE`를 `fake`→`real`로 전환(사용자 승인).
  `GeminiVisionProvider` 구현은 폴백 후보로 코드에 남겨둠(삭제 안 함).
- **비용 실측 비교** (5프레임 기준, 같은 입력): Claude Sonnet 5 input 3208/output 867
  토큰 → 호출당 $0.0151(인트로가). Gemini flash-latest input 6068/output 511 토큰 →
  $0.0065. Gemini가 지금 시점 ~2.3배 저렴하지만 실측 3회 중 2회 503(서버 과부하)로
  실패해서 안정성 문제 확인됨 — 최종적으로 안정성 우선해서 Claude로 확정.
- **회고 — 지금까지 놓친 것 사용자에게 보고, 4개 중 1번만 지금 처리하기로 결정**:
  1. **[처리함] Apify 재시도 미구현** — `docs/03-pipeline.md` collect "실패" 절이
     "3회 재시도(지수 백오프)"를 명시하는데 `ApifyCollectProvider._run()`엔 재시도가
     아예 없었음(명세 누락, T-1.2 때 놓쳤던 것). `APIFY_MAX_ATTEMPTS=4`(최초 1회+재시도
     3회), 지수 백오프(1s/2s/4s)로 수정. `httpx.HTTPError` 잡아서 재시도, 마지막까지
     실패하면 그대로 raise(호출부가 로그만 남기고 다음 릴스로 넘어가는 기존 원칙 유지).
     `tests/providers/test_collect_provider.py` 신규(2개, httpx mock — 실 API 호출
     아님): 2회 실패 후 성공 케이스, 최대 시도 후 실패 케이스. `asyncio.sleep`도
     mock해서 테스트 빠름(4초 이내). pytest 69개(67+2) 전부 통과.
  2. **[보류] DB 모듈/파이프라인 run() 자동화 테스트 없음** — accounts/reels/
     reel_metrics/shot_segments/reel_analyses, collect.run/score.run/frames.run/
     analyze.run 전부 1회성 스크립트로만 검증하고 삭제함. P0의 `requires_db` pytest
     관례를 안 따름 — 회귀 안전망 없음. P2 마무리 시점에 정리하기로 함.
  3. **[보류] fake 모드 vision fixture가 샷 1개 고정** — `fixtures/vision/sample.json`이
     컷 1개만 있어서, fake 모드에서 컷 2개 이상인 릴스는 analyze.py의 "샷 개수
     불일치→스킵" 로직 때문에 항상 스킵됨. fake 모드로 전체 파이프라인
     (collect→score→frames→analyze) 통합 테스트가 사실상 막혀있음.
  4. **[보류] 엔드투엔드 통합 테스트 없음** — `tests/worker/test_loop.py`는 단계를
     mock해서 실제 로직을 안 태움. 4단계가 실제로 이어져서 도는 자동 테스트 없음.
- **[처리함] 보류 3번 해결**: `FakeVisionProvider`가 fixture 샷 1개를 `frame_paths`
  개수만큼 복제해서 반환하도록 수정 — fake 모드에서 컷 개수 무관하게
  analyze.py의 "샷 개수 불일치→스킵" 가드에 안 걸리게 됨.
- **[처리함] 보류 2번(DB 자동화 테스트) 일부 해결**: `tests/db/test_pipeline_db.py`
  신규(6개) — accounts/reels/reel_metrics/shot_segments(부분커밋→VLM 갱신)/
  reel_analyses CRUD 왕복 + `collect.run()`→`score.run()` fake 모드 엔드투엔드.
  `clean_pipeline_tables` conftest 픽스처 신규(accounts CASCADE로 전 테이블 연쇄 정리).
  **frames.run()/analyze.run() 자동화는 여전히 보류** — 실제 mp4 다운로드(네트워크)와
  VLM 호출이 필요해서 로컬 HTTP서버+비디오 fixture 인프라 없이는 못 함, `.env`
  VISION_MODE=real이라 factory 경유 시 실과금 위험도 있음(테스트 파일 상단에 이유 기록).
- **[처리함] 보류 4번(엔드투엔드) 부분 해결**: collect→score 체인은 위 테스트로 커버됨.
  frames/analyze까지 포함한 전체 체인은 여전히 미커버(위와 같은 이유).

### P3 — compare.py(대조 분석) 구현
- **계약 애매한 지점 발견, 사용자 확인**: `score.select_breakout/control`이 B1+B2를
  하나로 묶어 다루는데(docs score 5번) `ComparisonResult.bucket`은 단일값 —
  사용자 결정: 비교 로직은 단일 비교 유지, `bucket` 필드엔 breakout 풀에 실제 존재하는
  가장 작은 버킷을 대표값으로(B1 있으면 B1). `compare.py`의 `_representative_bucket()`.
- `score.py` 리팩터링: `select_target_reels`가 내부에서만 쓰던 breakout/big_account/
  control `ScoredReel` 리스트를 `compute_tracks()`로 공개 분리(compare.py도 필요해짐).
- `app/db/shot_segments.py`: `get_completed()` 추가(VLM 필드 채워진 행만, idx순).
- `app/db/reel_analyses.py`: `get()` 추가.
- `app/pipeline/compare.py` 구현:
  - `compute_feature_findings`: angle/movement/purpose(첫 컷)는 샷 단위, subtitle_
    position/color_tone은 릴스 단위로 분모(total)를 다르게 계산 — docs가 이 둘을
    같은 방식으로 취급한다고 오해하기 쉬워서 명시적으로 분리함.
    gap_pp >= 30만 findings에 포함(계약 강제).
  - `compute_timing_stats`, `build_comparison_result`(n>=15 가드, 계약 불변식 5 강제).
  - `compute_comparison(keyword, business_type)`: reel_analyses+shot_segments 조인해서
    `ReelAnalysis` 재구성 → 없음 이유: **ComparisonResult를 담을 테이블이 스키마에
    없음**(docs comparing 절엔 "커밋" 행 자체가 없어서 이번엔 문서 오류 아님, 원래
    그렇게 설계된 것으로 확인) — guide.py(P4)도 이 함수 그대로 재사용해서 매번
    재계산하면 됨.
  - `tests/pipeline/test_compare_logic.py` 신규(6개): n가드, gap_pp 임계값 포함/제외,
    timing 평균 계산, 빈 그룹 처리.
  - DB 통합 테스트 1개 추가(`test_pipeline_db.py`): reel_analyses+shot_segments 조인
    경로 확인(표본 1개라 자연히 insufficient로 끝나는 케이스).
  - ruff/mypy 그린, pytest 82개 전부 통과.
### P4 — guide.py(가이드 생성) 구현, G4 게이트 도달
- **인터페이스 판단**: `WriterProvider.write_guide()`가 원래 `pool: ReelPool`을 받게
  돼 있었는데, `ReelPool.collected_count` 등 집계 필드가 P1부터 어디에도 저장 안 되는
  값이라(이미 기록된 갭) 채우려면 지어내야 했음 — 프롬프트가 실제 쓰는 건 breakout/
  big_account의 `ReelAnalysis`뿐이라 인터페이스를 `breakout: list[ReelAnalysis],
  big_account: list[ReelAnalysis]`로 좁힘(`ReelPool` 자체를 안 씀). 판단이라 사용자
  확인 안 받고 바로 처리 — 순수 내부 인터페이스 변경이고 출력 품질에 영향 없음.
- **워커 버그 사전 발견 및 수정**: `worker/loop.py`의 `process_job()`이 스테이지 다
  돌고 나서 `mark_done(job.id)`을 인자 없이 불러서 **jobs.result가 영원히 None**이
  되는 구조였음(P0~P3는 guide.py가 빈 스텁이라 문제 없었는데 지금부터 실제 버그가
  됨). `guides_db.get_latest_by_job(job.id)`로 방금 커밋한 Guide를 다시 읽어서
  `mark_done(job.id, result=guide_result)`로 넘기게 고침.
- `app/db/guides.py`(신설): `create()`, `get_latest_by_job()`.
- `compare.py`의 `_build_reel_analysis` → `build_reel_analysis`로 공개화(guide.py도
  재사용).
- `app/pipeline/guide.py` 구현:
  - `compute_confidence`(docs 02-contracts 판정표 그대로: sufficient+findings>=2
    →충분, sufficient+findings<=1→제한적, insufficient→불충분).
  - `filter_reference_shots`(docs generating 1번): shooting_alone→촬영자 필요 샷은
    solo_alternative로 치환(없으면 제외), can_show_face=False→"얼굴" 문자열 포함 샷
    제외(VLM에 별도 필드 없어서 휴리스틱, 한계 있음 — 판단), equipment에 없는 장비
    요구 샷 제외.
  - `render_user_prompt`: prompts/guide_writer.md 템플릿에 `{placeholder} ← 주석`
    형태로 개발자용 화살표 주석이 코드펜스 안에 그대로 박혀 있는 걸 발견 —
    정규식으로 스킵(모델에게 안 보내야 함, 안 그러면 그대로 프롬프트에 섞여 들어감).
    `{my_reel_block}`은 P5 미구현이라 항상 그 줄 자체를 제거.
  - `_week_of`: ISO 주 시작(월요일) 기준, 문서에 명시 없어 판단.
  - `ClaudeWriterProvider` 구현: `claude-sonnet-5`(vision과 같은 비용 판단),
    structured outputs로 Guide 스키마 강제, 검증 실패 시 1회 재시도(docs 명시).
  - `tests/pipeline/test_guide_logic.py` 신규(12개): confidence 판정 3가지,
    필터링 5가지(대안 치환/제외/얼굴/장비 있음·없음), 프롬프트 렌더링(화살표 제거,
    my_reel_block 제거, 불충분 케이스), week_of.
  - `tests/db/test_pipeline_db.py`에 guides 왕복 테스트 추가.
  - ruff/mypy 그린, pytest 95개 전부 통과.
- **실측 검증 (실제 Claude API 호출, 소액 과금)**: 합성 ComparisonResult(충분,
  findings 2개) + breakout 2개/big_account 1개 ReelAnalysis로 `ClaudeWriterProvider.
  write_guide()` 직접 호출. **결과 정상**: shot_list 8개(솔로 대안 정확히 반영 —
  "촬영자 1명" 요구 샷을 "폰을 삼각대에 고정" 식으로 치환, 얼굴 노출 불가 조건도
  "어깨 아래만 프레임"으로 반영), caption_drafts 4개, confidence="충분",
  caveat에 표본 한계 명시.
  - **프롬프트 품질 이슈 발견**: `evidence_note`에서 "각각 61%p, 58%p 확인됨"처럼
    **퍼센트만 쓰고 원시 개수를 병기 안 한 문장**이 나옴 — CLAUDE.md 금지 목록
    "리포트에 퍼센트만 쓰기 금지 (반드시 '18개 중 14개' 형태 병기)" 위반. system
    프롬프트엔 이미 이 규칙이 있는데(`"83%" X → "18개 중 14개" O`) 이 문장에서는
    안 지켜짐 — G4 게이트에서 사용자에게 보고하고 프롬프트 보강 여부 물어볼 것.
- **[처리함] 프롬프트 품질 이슈 해결**: 사용자 결정("잡을 수 있으면 잡고 넘어가자")에 따라
  `prompts/guide_writer.md`와 `docs/04-prompts.md`(둘 다, 관례대로 동기화) system 프롬프트에
  evidence_note 전용 규칙 명시 추가 — "이 규칙은 evidence_note 필드에도 그대로 적용됩니다.
  '각각 61%p, 58%p 확인됨' X → '18개 중 14개(78%), 16개 중 11개(69%)에서 확인됨' O.
  퍼센트/%p 단독 표기는 금지합니다." + User 템플릿 JSON 스키마의 evidence_note 자리에도
  괄호로 규칙 재강조. **재검증(실제 Claude API 호출)**: 동일 fixture로 재실행 →
  evidence_note가 "상위 18개 중 14개(탑뷰), 하위 16개 중 3개에서 탑뷰 구도 확인됨(차이
  61%p). 자막 하단 배치는 상위 18개 중 15개, 하위 16개 중 4개에서 확인됨(차이 58%p)."로
  개선 확인 — 원시개수 병기 규칙 준수. ruff/mypy/pytest(95개) 그린 재확인.
- **G4 게이트 승인**: 프롬프트 보강 완료로 사용자 승인. P5(내 릴스 진단)로 진행.
