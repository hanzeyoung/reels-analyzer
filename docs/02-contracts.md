# 02 — 계약 (CONTRACTS)

> **이 문서가 유일한 진실이다.**
> 코드가 이 문서와 다르면 코드가 틀린 것이다.
> 변경이 필요하면 코드를 고치지 말고 **멈추고 사용자에게 물어라.**

전 모델 공통:
```python
model_config = ConfigDict(extra="forbid")
```

---

## 0. 공통 타입

```python
from typing import Literal
from datetime import datetime, date
from uuid import UUID

Bucket = Literal["B1", "B2", "B3", "B4", "unknown"]
Track  = Literal["breakout", "big_account", "control"]

JobStatus = Literal["queued", "running", "done", "failed"]
JobStage  = Literal["collecting", "scoring", "preparing",
                    "analyzing", "comparing", "generating"]

Movement   = Literal["고정", "패닝", "줌", "따라가기", "핸드헬드"]
ShotPurpose = Literal["후킹", "정보", "전환", "마무리", "CTA"]
Difficulty  = Literal["하", "중", "상"]
Confidence  = Literal["충분", "제한적", "불충분"]
```

**버킷 경계 (초기 고정값)**

| 버킷 | 팔로워 |
|---|---|
| B1 | ~1,000 |
| B2 | 1,000 ~ 10,000 |
| B3 | 10,000 ~ 100,000 |
| B4 | 100,000 ~ |
| unknown | 팔로워 데이터 없음 |

해당 업종 누적 200건 초과 시 업종별 33/66 분위수로 교체. 경계는 `bucket_configs`에 저장.

---

## 1. 입력

```python
class UserConstraints(BaseModel):
    shooting_alone: bool = True
    equipment: list[str] = ["스마트폰"]
    space: Literal["좁음", "보통", "넓음"] = "보통"
    can_show_face: bool = False
    weekly_minutes: int = 60

class AnalysisRequest(BaseModel):
    keyword: str                      # "성수동카페"
    business_type: str                # "카페"
    constraints: UserConstraints
    my_reel_url: str | None = None    # P5. 있으면 진단 카드 생성
```

---

## 2. 수집 단계 (collect)

```python
class RawReel(BaseModel):
    """Apify 응답을 정규화한 형태. 어댑터가 이 모양으로 변환한다."""
    code: str                       # 릴스 shortcode. 전 시스템의 기본 키
    url: str
    username: str
    caption: str = ""
    hashtags: list[str] = []        # 캡션에서 정규식으로 추출
    audio_title: str | None = None
    video_url: str | None = None
    thumbnail_url: str | None = None
    duration_sec: float | None = None
    taken_at: datetime

    play_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    # save_count 없음 — Apify가 제공하지 않는다. share가 그 역할을 대신한다.


class Account(BaseModel):
    username: str
    follower_count: int | None = None   # ★ None 허용. 0으로 채우지 마라
    fetched_at: datetime | None = None  # 30일 캐시 판정용
```

**`follower_count is None`의 의미**: "0명"이 아니라 **"모른다"**.
이 값이 None이면 파이프라인이 반응률 단독 축으로 자동 전환된다.

---

## 3. 스코어 단계 (score)

```python
class ReelMetrics(BaseModel):
    engagement_rate: float            # (like+comment+share) / play. 항상 계산 가능
    share_rate: float                 # share / play
    reach_multiple: float | None      # play / follower. 팔로워 있을 때만

class ScoredReel(BaseModel):
    reel: RawReel
    account: Account
    metrics: ReelMetrics
    bucket: Bucket
    track: Track | None = None        # 선정 단계에서 채워짐
```

**지표 2축**

| 지표 | 의미 | 팔로워 필요 |
|---|---|---|
| `engagement_rate` | 본 사람을 얼마나 붙잡았나 = 콘텐츠 질 | ✗ |
| `reach_multiple` | 체급 대비 얼마나 퍼졌나 = 돌파력 | ✓ |

---

## 4. 선정 단계 (select)

```python
class ReelPool(BaseModel):
    keyword: str
    business_type: str

    collected_count: int              # 수집 원본 개수
    after_recency_count: int          # 30일 필터 통과
    after_relevance_count: int        # 관련성 필터 통과
    after_dedup_count: int            # 중복 제거 후 = 실질 표본

    follower_data_available: bool     # False면 bucket 전부 "unknown"
    bucket_config_id: str | None

    breakout: list[ScoredReel]        # B1+B2 & reach_multiple 상위
    big_account: list[ScoredReel]     # B4 & play_count 상위
    control: list[ScoredReel]         # breakout과 같은 버킷의 하위
```

**트랙별 용도 (프롬프트에서 반드시 지킨다)**

| 트랙 | 쓰는 곳 | 쓰면 안 되는 곳 |
|---|---|---|
| `breakout` | 샷 리스트, 촬영 팁, 자막 카피 | — |
| `big_account` | 음원, 소재, 해시태그 | **촬영 기법** (못 따라한다) |
| `control` | 대조 비교 | 가이드 직접 인용 |

---

## 5. 컷 분해 단계 (frames)

```python
class Cut(BaseModel):
    index: int                        # 0부터
    t_start: float                    # 초
    t_end: float
    frame_path: str                   # 임시 파일. 분석 후 삭제

class CutList(BaseModel):
    reel_code: str
    duration_sec: float
    cuts: list[Cut]
    cut_count: int
    avg_shot_sec: float
    first_shot_sec: float             # 첫 컷 길이. 후킹 지표
    source: Literal["ffmpeg_scene_detect"] = "ffmpeg_scene_detect"
```

**타임스탬프는 오직 ffmpeg에서 나온다.** VLM에게 시각을 묻지 않는다.
샘플링된 프레임만 보고 컷 경계를 추정하는 것은 구조적으로 불가능하며, 모델은 그럴듯한 숫자를 지어낸다.

---

## 6. 분석 단계 (analyze)

### 6-1. VLM 출력 원형 — **시각 정보 없음**

```python
class VisionShotDescription(BaseModel):
    """VLM이 반환하는 형태. t_start/t_end가 없는 것이 의도적이다."""
    index: int                        # 입력 프레임 순서와 동일해야 함
    angle: str                        # 탑뷰 / 클로즈업 / 정면샷 / 하이앵글 ...
    subject: str                      # "커피 붓는 손"
    on_screen_text: str | None        # 화면 자막 원문 그대로
    movement: Movement
    purpose: ShotPurpose
    technique: str | None             # 특기할 기법
    difficulty: Difficulty
    requires: list[str] = []          # ["짐벌", "촬영자 1명"]
    solo_alternative: str | None      # 혼자 찍을 때 대안

class VisionAnalysis(BaseModel):
    shots: list[VisionShotDescription]
    caption_hooks: list[str] = []
    color_tone: str
    subtitle_position: Literal["상단", "중앙", "하단", "혼합", "없음"]
    summary: str                      # 소상공인 눈높이 2~3줄
```

### 6-2. 병합 결과 — 파이프라인이 시각을 주입

```python
class ShotSegment(VisionShotDescription):
    t_start: float                    # CutList에서 주입
    t_end: float

class ReelAnalysis(BaseModel):
    reel_code: str
    track: Track
    bucket: Bucket
    shots: list[ShotSegment]
    caption_hooks: list[str]
    color_tone: str
    subtitle_position: str
    summary: str
    cut_count: int
    avg_shot_sec: float
    first_shot_sec: float
    audio_title: str | None
    model: str                        # "claude-..." 실제 사용 모델
    analyzed_at: datetime
```

**책임 분리**

| 값 | 출처 |
|---|---|
| `cut_count`, `avg_shot_sec`, `first_shot_sec`, `t_start`, `t_end` | ffmpeg (정확) |
| `angle`, `subject`, `on_screen_text`, `movement` | VLM (서술) |

섞지 마라.

---

## 7. 대조 단계 (compare)

```python
class FeatureCount(BaseModel):
    value: str                        # "탑뷰"
    count: int                        # 14
    total: int                        # 18
    # 표기: "18개 중 14개". 퍼센트 단독 사용 금지

class DifferenceFinding(BaseModel):
    feature: str                      # "촬영 구도"
    high: FeatureCount
    low: FeatureCount
    gap_pp: float                     # 비율 차이 (percentage point)

class TimingStats(BaseModel):
    first_shot_sec_high: float
    first_shot_sec_low: float
    avg_shot_sec_high: float
    avg_shot_sec_low: float
    cut_count_high: float
    cut_count_low: float

class ComparisonResult(BaseModel):
    bucket: Bucket
    high_n: int
    low_n: int
    sufficient: bool                  # high_n >= 15 and low_n >= 15
    findings: list[DifferenceFinding] # sufficient=False면 반드시 빈 리스트
    timing: TimingStats | None
    insufficient_reason: str | None
```

**가드 (절대 규칙)**

- `high_n < 15` 또는 `low_n < 15` → `sufficient=False`, `findings=[]`
- `gap_pp < 30` 인 항목은 `findings`에 넣지 않는다
- 이 두 조건은 코드에서 강제한다. 프롬프트로 부탁하지 마라.

---

## 8. 가이드 단계 (generate) — 최종 산출물

```python
class ShotListItem(BaseModel):
    order: int
    t_start_sec: float
    duration_sec: float
    angle: str
    subject: str
    on_screen_text: str | None
    note: str                         # 촬영 요령 1줄

class CaptionDraft(BaseModel):
    text: str
    pattern: str                      # "숫자 포함" "질문형" ...

class AudioRecommendation(BaseModel):
    title: str
    seen_count: int
    total: int

class DiagnosisCard(BaseModel):
    metric: str                       # "첫 컷 길이"
    mine: str                         # "5.2초"
    benchmark: str                    # "1.8초"
    gap_note: str                     # 한 줄 해석

class Guide(BaseModel):
    business_type: str
    keyword: str
    week_of: date

    shot_list: list[ShotListItem]
    caption_drafts: list[CaptionDraft]
    audio: list[AudioRecommendation]
    diagnosis: list[DiagnosisCard] = []   # my_reel_url 없으면 빈 리스트

    evidence_note: str                # "최근 30일, 팔로워 1천~1만 구간 18개 기준"
    confidence: Confidence
    caveat: str | None                # confidence != "충분"일 때 필수
```

**`confidence` 판정**

| 값 | 조건 |
|---|---|
| 충분 | `ComparisonResult.sufficient=True` 이고 `findings` 2개 이상 |
| 제한적 | sufficient=True 이나 findings 1개 이하 |
| 불충분 | sufficient=False |

`불충분`이면 샷 리스트는 **돌파형 상위 1개를 그대로 해체한 형태**로 제공하고,
`caveat`에 표본 부족을 명시한다. **없는 패턴을 만들어내지 않는다.**

---

## 9. 잡

```python
class Job(BaseModel):
    id: UUID
    status: JobStatus
    stage: JobStage | None = None
    progress_current: int = 0
    progress_total: int = 0
    error: str | None = None
    heartbeat_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    request: AnalysisRequest
    result: Guide | None = None
```

---

## 10. 계약 불변식 (테스트로 강제)

1. `RawReel.code`는 전 시스템의 기본 키. 다른 식별자를 만들지 마라.
2. `Account.follower_count`가 None이면 `ReelMetrics.reach_multiple`도 반드시 None.
3. `ShotSegment.t_start < t_end`, 리스트는 `t_start` 오름차순.
4. `len(VisionAnalysis.shots) == len(CutList.cuts)`. 다르면 분석 실패로 처리.
5. `ComparisonResult.sufficient == False` → `findings == []`.
6. `Guide.confidence != "충분"` → `caveat is not None`.
7. `FeatureCount.count <= total`.
