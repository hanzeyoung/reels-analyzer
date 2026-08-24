"""JobStage 'comparing'. 순수 Python 통계, LLM 호출 없음.
docs/03-pipeline.md의 comparing 참조 (P3 구현).

score.select_breakout()/select_control()은 B1+B2를 하나로 묶어서 다룬다(docs score
5번: "B1+B2 중 reach_multiple 상위"). 그런데 `ComparisonResult.bucket`은 단일값이라
표시할 대표 버킷 하나를 정해야 한다 — 사용자 판단(2026-08-14): 비교 로직 자체는 단일
비교로 유지하고, `bucket` 필드엔 breakout 풀에 실제 존재하는 가장 작은 버킷을
대표값으로 넣는다(B1이 있으면 B1, 없으면 B2 등). 표시용 라벨일 뿐 통계에는 영향 없다.
"""

import logging
from collections.abc import Callable
from uuid import UUID

from app.db import jobs as jobs_db
from app.db import reel_analyses as reel_analyses_db
from app.db import shot_segments as shot_segments_db
from app.pipeline.score import compute_tracks
from app.schemas.analyze import ReelAnalysis, ShotSegment
from app.schemas.common import Bucket, Track
from app.schemas.compare import ComparisonResult, DifferenceFinding, FeatureCount, TimingStats
from app.schemas.score import ScoredReel

logger = logging.getLogger(__name__)

MIN_GROUP_N = 15  # docs/02-contracts.md 계약 불변식 5: high_n/low_n >= 15
MIN_GAP_PP = 30.0  # docs/03-pipeline.md comparing 4번: 30%p 미만은 findings 제외

_BUCKET_PRIORITY: list[Bucket] = ["B1", "B2", "B3", "B4", "unknown"]


def _representative_bucket(reel_analyses: list[ReelAnalysis]) -> Bucket:
    buckets = {ra.bucket for ra in reel_analyses}
    for candidate in _BUCKET_PRIORITY:
        if candidate in buckets:
            return candidate
    return "unknown"


def _angle_values(group: list[ReelAnalysis]) -> list[str]:
    return [shot.angle for ra in group for shot in ra.shots]


def _movement_values(group: list[ReelAnalysis]) -> list[str]:
    return [shot.movement for ra in group for shot in ra.shots]


def _subtitle_position_values(group: list[ReelAnalysis]) -> list[str]:
    return [ra.subtitle_position for ra in group]


def _color_tone_values(group: list[ReelAnalysis]) -> list[str]:
    return [ra.color_tone for ra in group]


def _first_cut_purpose_values(group: list[ReelAnalysis]) -> list[str]:
    return [ra.shots[0].purpose for ra in group if ra.shots]


# docs/03-pipeline.md comparing 2번: "angle, movement, subtitle_position, color_tone,
# purpose(첫 컷)". angle/movement/purpose는 샷 단위, subtitle_position/color_tone은
# 릴스 단위 값이라 total(분모)이 서로 다르다 — extractor가 각자 맞는 단위로 뽑는다.
_FEATURE_EXTRACTORS: dict[str, Callable[[list[ReelAnalysis]], list[str]]] = {
    "구도(angle)": _angle_values,
    "카메라 움직임(movement)": _movement_values,
    "자막 위치(subtitle_position)": _subtitle_position_values,
    "색감(color_tone)": _color_tone_values,
    "첫 컷 목적(purpose)": _first_cut_purpose_values,
}


def compute_feature_findings(
    high: list[ReelAnalysis], low: list[ReelAnalysis]
) -> list[DifferenceFinding]:
    """비율 차이 30%p 이상인 항목만 반환한다 (docs comparing 2·4번)."""
    findings: list[DifferenceFinding] = []
    for feature_name, extractor in _FEATURE_EXTRACTORS.items():
        high_values = extractor(high)
        low_values = extractor(low)
        if not high_values or not low_values:
            continue
        high_total, low_total = len(high_values), len(low_values)
        for value in sorted({*high_values, *low_values}):
            high_count = high_values.count(value)
            low_count = low_values.count(value)
            gap_pp = abs(high_count / high_total * 100 - low_count / low_total * 100)
            if gap_pp < MIN_GAP_PP:
                continue
            findings.append(
                DifferenceFinding(
                    feature=feature_name,
                    high=FeatureCount(value=value, count=high_count, total=high_total),
                    low=FeatureCount(value=value, count=low_count, total=low_total),
                    gap_pp=gap_pp,
                )
            )
    return findings


def compute_timing_stats(high: list[ReelAnalysis], low: list[ReelAnalysis]) -> TimingStats:
    """docs comparing 5번: 첫 컷 길이·평균 샷 길이·컷 수를 그룹별 평균으로."""

    def avg(xs: list[float]) -> float:
        return sum(xs) / len(xs)

    return TimingStats(
        first_shot_sec_high=avg([ra.first_shot_sec for ra in high]),
        first_shot_sec_low=avg([ra.first_shot_sec for ra in low]),
        avg_shot_sec_high=avg([ra.avg_shot_sec for ra in high]),
        avg_shot_sec_low=avg([ra.avg_shot_sec for ra in low]),
        cut_count_high=avg([ra.cut_count for ra in high]),
        cut_count_low=avg([ra.cut_count for ra in low]),
    )


def build_comparison_result(
    high: list[ReelAnalysis], low: list[ReelAnalysis]
) -> ComparisonResult:
    """`high`=breakout, `low`=control (docs comparing 1번). n 가드는 코드로 강제한다
    (docs comparing 3번, 계약 불변식 5) — 프롬프트로 부탁하지 않는다."""
    high_n, low_n = len(high), len(low)
    bucket = _representative_bucket(high or low)

    if high_n < MIN_GROUP_N or low_n < MIN_GROUP_N:
        return ComparisonResult(
            bucket=bucket,
            high_n=high_n,
            low_n=low_n,
            sufficient=False,
            findings=[],
            timing=None,
            insufficient_reason=(
                f"표본 부족: 돌파형 {high_n}개, 대조군 {low_n}개 (각각 최소 {MIN_GROUP_N}개 필요)"
            ),
        )

    return ComparisonResult(
        bucket=bucket,
        high_n=high_n,
        low_n=low_n,
        sufficient=True,
        findings=compute_feature_findings(high, low),
        timing=compute_timing_stats(high, low),
        insufficient_reason=None,
    )


async def _build_reel_analysis(
    reel_code: str, track: Track, bucket: Bucket, audio_title: str | None
) -> ReelAnalysis | None:
    """reel_analyses + shot_segments를 조인해서 `ReelAnalysis`를 재구성한다.
    analyzing이 아직 안 끝났거나 실패한 릴스는 None(호출부가 제외한다)."""
    summary = await reel_analyses_db.get(reel_code)
    if summary is None:
        return None
    shot_rows = await shot_segments_db.get_completed(reel_code)
    if not shot_rows:
        return None

    shots = [
        ShotSegment(
            index=row["idx"],
            t_start=row["t_start"],
            t_end=row["t_end"],
            angle=row["angle"],
            subject=row["subject"],
            on_screen_text=row["on_screen_text"],
            movement=row["movement"],
            purpose=row["purpose"],
            technique=row["technique"],
            difficulty=row["difficulty"],
            requires=row["requires"],
            solo_alternative=row["solo_alternative"],
        )
        for row in shot_rows
    ]
    return ReelAnalysis(
        reel_code=reel_code,
        track=track,
        bucket=bucket,
        shots=shots,
        caption_hooks=summary["caption_hooks"],
        color_tone=summary["color_tone"],
        subtitle_position=summary["subtitle_position"],
        summary=summary["summary"],
        cut_count=summary["cut_count"],
        avg_shot_sec=summary["avg_shot_sec"],
        first_shot_sec=summary["first_shot_sec"],
        audio_title=audio_title,
        model=summary["model"],
        analyzed_at=summary["analyzed_at"],
    )


async def build_reel_analysis(scored: ScoredReel, track: Track) -> ReelAnalysis | None:
    return await _build_reel_analysis(
        scored.reel.code, track, scored.bucket, scored.reel.audio_title
    )


async def build_my_reel_analysis(reel_code: str, audio_title: str | None) -> ReelAnalysis | None:
    """P5(내 릴스 진단). 버킷 분류 대상이 아니라 `bucket="unknown"`으로 고정한다."""
    return await _build_reel_analysis(reel_code, "my_reel", "unknown", audio_title)


async def compute_comparison(keyword: str, business_type: str) -> ComparisonResult:
    """generating(guide.py, P4)도 이 함수를 그대로 재사용한다 — ComparisonResult를
    담을 테이블이 스키마에 없어서(docs comparing 절엔 "커밋" 항목 자체가 없다) 저장 없이
    매번 재계산한다. reel_analyses+shot_segments만 있으면 결정론적으로 같은 결과가 나온다."""
    breakout, _big_account, control = await compute_tracks(keyword, business_type)

    high: list[ReelAnalysis] = []
    for scored in breakout:
        analysis = await build_reel_analysis(scored, "breakout")
        if analysis is not None:
            high.append(analysis)

    low: list[ReelAnalysis] = []
    for scored in control:
        analysis = await build_reel_analysis(scored, "control")
        if analysis is not None:
            low.append(analysis)

    return build_comparison_result(high, low)


async def run(job_id: str) -> None:
    job = await jobs_db.get_job(UUID(job_id))
    assert job is not None, f"job {job_id} not found"
    keyword = job.request.keyword
    business_type = job.request.business_type

    result = await compute_comparison(keyword, business_type)
    logger.info(
        "job %s 대조 분석 완료: bucket=%s, high_n=%d, low_n=%d, sufficient=%s, findings=%d",
        job_id,
        result.bucket,
        result.high_n,
        result.low_n,
        result.sufficient,
        len(result.findings),
    )
