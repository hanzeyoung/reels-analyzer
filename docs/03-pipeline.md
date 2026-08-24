# 03 — 파이프라인

각 단계는 **입력 계약 → 출력 계약**이 고정되어 있다. `docs/02-contracts.md` 참조.

---

## collect

| | |
|---|---|
| 입력 | `AnalysisRequest` |
| 출력 | `list[RawReel]` + `list[Account]` |
| 커밋 | `reels`, `accounts` 테이블 |

1. Apify 호출. **키워드당 150~200건** (30일 필터로 절반 이상 날아간다)
2. `is_video=True` and `video_url` 존재하는 것만
3. 캡션에서 `#\w+` 정규식으로 `hashtags` 추출
4. **최근 30일 필터** — `taken_at`이 30일 이내가 아니면 버림
5. 관련성 필터 — 키워드가 캡션/해시태그/계정명/위치명에 있는지.
   복합어는 어절 분해 후 3개 이하면 전부, 초과면 75% 이상 매칭
6. 중복 제거 — 캡션 정규화 후 `SequenceMatcher >= 0.82` 이면 동일 콘텐츠로 간주
7. 계정 정보: `accounts`에 `fetched_at`이 30일 이내면 재사용, 아니면 조회

**실패**: Apify 실패 시 3회 재시도(지수 백오프). 그래도 실패면 잡 `failed`.

---

## score

| | |
|---|---|
| 입력 | `list[RawReel]`, `list[Account]` |
| 출력 | `ReelPool` |
| 커밋 | `reel_metrics` |

1. `engagement_rate = (like+comment+share) / max(play, 1)`
2. `share_rate = share / max(play, 1)`
3. 팔로워 있으면 `reach_multiple = play / max(follower, 1)`, 없으면 None
4. 버킷 분류. 팔로워 없으면 전부 `unknown`
5. 트랙 선정:
   - `breakout` — B1+B2 중 `reach_multiple` 상위. 팔로워 없으면 `engagement_rate` 상위
   - `big_account` — B4 중 `play_count` 상위. 팔로워 없으면 **빈 리스트**
   - `control` — breakout과 같은 버킷의 하위

**`follower_data_available=False`일 때 동작**
- 버킷 없음. 전체를 하나로 보고 `engagement_rate` 상하위 비교
- `big_account` 트랙 비활성 → 음원 추천은 전체 상위에서 뽑음
- `Guide.evidence_note`에 팔로워 데이터 부재를 명시

---

## preparing

> **G0 수정 (계약 충돌 정정)**: 원래 이 단계는 `downloading`이라는 이름으로 mp4 다운로드만
> 담당하고, ffmpeg scene detect·프레임 추출까지 전부 `analyzing`에 묶여 있었다.
> P0 워커 구현 중 "로컬·결정론적 작업(ffmpeg)"과 "과금·비결정론적 호출(VLM)"을 같은
> JobStage로 묶으면 재시작 단위·과금 관측 단위가 뒤섞인다는 문제가 드러나 분리했다.
> `JobStage` 값도 `downloading` → `preparing`으로 바꿨다 (`analyzing`은 이제 VLM 호출만).

| | |
|---|---|
| 입력 | `ReelPool` |
| 출력 | 릴스별 `CutList` + 임시 대표 프레임 파일 |
| 커밋 | `shot_segments`에 `t_start`/`t_end`/`idx`만 먼저 INSERT (VLM 필드는 NULL로 남김) |

> **정정 (P2, 2026-08-14)**: 원래 "커밋 없음"이라 적혀 있었으나 `docs/06-db.md`의
> `shot_segments` 스키마(`t_start`/`t_end`는 NOT NULL, `angle`/`subject` 등 VLM 필드는
> nullable)와 아래 "이미 분석 결과가 있는 code는 다운로드를 건너뛴다"는 스킵 로직이
> 실제로 성립하려면 **frames.py가 t_start/t_end/idx만 먼저 커밋**해야 앞뒤가 맞는다.
> 워커가 단계 간 job_id로만 통신(메모리 전달 없음)해서 `CutList`를 "그대로 전달"할
> DB 외의 방법이 없었다 — 문서 오류로 보고 정정. `analyzing` 단계가 같은 행을
> VLM 필드로 UPDATE한다.

- `breakout` + `big_account` + `control` 대상만 다운로드
- `shot_segments`에 이미 분석 결과가 있는 `code`는 **다운로드 자체를 건너뛴다** (VLM뿐 아니라 ffmpeg도 재실행하지 않는다)
1. mp4 다운로드
2. **ffmpeg scene detect** → 컷 경계 (`CutList`)
   ```
   ffmpeg -i in.mp4 -vf "select='gt(scene,0.3)',showinfo" -f null -
   ```
   또는 PySceneDetect `ContentDetector`. 임계값은 설정값으로 뺀다.
3. 컷 수가 3 미만이면 균등 5분할로 폴백 (단일 컷 롱테이크 릴스 대응)
4. 컷마다 **대표 프레임 1장** 추출 (컷 중앙 지점)
5. phash로 유사 프레임 제거. 최대 12장 상한
- 실패한 릴스는 로그만 남기고 계속 진행 (전체 실패 아님)

---

## analyzing

| | |
|---|---|
| 입력 | `CutList` + 대표 프레임 (`preparing` 산출물) |
| 출력 | `list[ReelAnalysis]` |
| 커밋 | 릴스 1개마다 즉시 `shot_segments` |

릴스 1개당:
1. VLM 호출 → `VisionAnalysis`
2. `len(shots) != len(cuts)`면 1회 재시도, 그래도 다르면 해당 릴스 스킵
3. `CutList`의 시각을 주입해 `ReelAnalysis` 완성
4. **mp4 즉시 삭제**
5. `progress_current` 갱신

**비용 방어**: `preparing` 단계에서 이미 `shot_segments` 존재 여부로 다운로드·ffmpeg 자체를 걸렀기 때문에, 여기 도달한 릴스는 전부 VLM 호출 대상이다.

---

## comparing

| | |
|---|---|
| 입력 | `list[ReelAnalysis]` |
| 출력 | `ComparisonResult` |

1. 같은 버킷 내에서만 상위(breakout) vs 하위(control) 그룹 구성
2. 특성별 빈도 집계: `angle`, `movement`, `subtitle_position`, `color_tone`, `purpose`(첫 컷)
3. **n 가드**: 어느 한쪽이라도 15 미만 → `sufficient=False`, `findings=[]`, 종료
4. 비율 차이 30%p 이상인 항목만 `findings`에 포함
5. `TimingStats` 계산 (첫 컷 길이, 평균 샷 길이, 컷 수)

이 단계는 **순수 Python이다. LLM 호출 없음.** 통계를 모델에게 맡기지 마라.

---

## diagnosing (P5)

| | |
|---|---|
| 입력 | `AnalysisRequest.my_reel_url` |
| 출력 | 내 릴스의 `ReelAnalysis` (`track="my_reel"`) |
| 커밋 | `reels`(`is_my_reel=true`) + `shot_segments` + `reel_analyses` |

`my_reel_url`이 `None`이면 즉시 스킵한다(진단 카드 없이 진행).

1. Apify로 URL 하나만 조회(`CollectProvider.fetch_reel_by_url`) → `RawReel`
2. `reels`에 `is_my_reel=true`로 upsert — 키워드 풀 조회(`get_by_keyword`)에서 항상
   제외되므로 버킷 분류·대조 분석 표본을 오염시키지 않는다
3. `preparing`/`analyzing`과 동일한 로직(`frames.process_reel`/`analyze.process_reel`
   재사용)으로 컷 분해 + VLM 샷 서술
4. 실패(포스트 삭제/비공개, 다운로드 실패 등)해도 잡 전체를 막지 않는다 — 로그만 남기고
   진단 카드 없이 진행(실패 원칙과 동일)

`comparing`과 순서상 독립적이지만(내 릴스 분석은 풀 비교와 무관), `generating`이 벤치마크로
쓸 `ComparisonResult.timing`이 먼저 있어야 하므로 `comparing` 다음, `generating` 직전에 둔다.

---

## generating

| | |
|---|---|
| 입력 | `ComparisonResult`, `ReelPool`, `UserConstraints`, `confidence`(코드가 계산), 내 릴스 `ReelAnalysis`(있으면) |
| 출력 | `Guide` |
| 커밋 | `guides` |

0. `confidence`는 `ComparisonResult.sufficient`/`findings` 개수로 **이 단계 진입 전에 코드가 계산**해서
   `WriterProvider.write_guide(comparison, pool, constraints, confidence)`의 인자로 넘긴다.
   `Guide.confidence != "충분"`이면 `caveat`이 필수이므로, 모델에 confidence를 넘기지 않고
   모델이 알아서 판단하게 하면 계약을 못 지킬 수 있다.
1. `UserConstraints`로 재현 불가 기법 필터링
   - `shooting_alone=True` → `requires`에 "촬영자" 포함된 샷은 `solo_alternative`로 치환.
     대안이 없으면 제외
   - `can_show_face=False` → 인물 얼굴이 주 피사체인 샷 제외
   - `equipment`에 없는 장비를 요구하는 샷 제외
2. 내 릴스 `ReelAnalysis`가 있으면 컷 수/평균 샷 길이/첫 컷 길이를 `ComparisonResult.timing`
   (breakout 평균, 벤치마크)과 함께 `{my_reel_block}`에 채운다. 없으면 그 블록 자체를
   프롬프트에서 제거(`diagnosis`는 빈 리스트로 남는다)
3. Claude 호출 (`docs/04-prompts.md`)
4. 반환 JSON을 `Guide`로 검증. 실패 시 1회 재시도
5. `confidence` 값 자체는 **코드에서 계산한 값을 그대로 덮어쓴다.** 모델 출력의 confidence는 신뢰하지 않는다

---

## 실패 원칙

| 상황 | 처리 |
|---|---|
| 릴스 1개 다운로드/분석 실패 | 로그만, 계속 진행 |
| 단계 전체 실패 | 잡 `failed` + `error` 기록, 워커는 다음 잡으로 |
| 워커 프로세스 사망 | heartbeat 만료 → `queued` 복귀, 해당 stage부터 재개 |
| VLM JSON 파싱 실패 | 1회 재시도 → 실패 시 해당 릴스 스킵 |
