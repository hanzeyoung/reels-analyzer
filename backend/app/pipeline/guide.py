"""JobStage 'generating'. 최종 Guide 작성. docs/03-pipeline.md의 generating 참조 (P4 구현).

`ComparisonResult`/`ReelAnalysis`를 담을 테이블이 없어서(compare.py와 동일한 이유)
compare.compute_comparison()/score.compute_tracks()를 다시 호출해 재구성한다.
"""

import logging
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from app.db import guides as guides_db
from app.db import jobs as jobs_db
from app.db import reels as reels_db
from app.pipeline import compare, score
from app.schemas.analyze import ReelAnalysis, ShotSegment
from app.schemas.common import Confidence
from app.schemas.compare import ComparisonResult
from app.schemas.requests import UserConstraints

logger = logging.getLogger(__name__)

# docs/02-contracts.md "confidence 판정" 표.
CONFIDENCE_SUFFICIENT_MIN_FINDINGS = 2

# prompts/guide_writer.md의 User 템플릿엔 "{placeholder}  ← 없으면 ..." 형태로 개발자용
# 주석이 코드펜스 안에 그대로 박혀 있다 — 실제 모델에게는 안 보내야 한다(판단, 2026-08-14).
_ARROW_COMMENT_RE = re.compile(r"[ \t]*←.*$", re.MULTILINE)
_MY_REEL_BLOCK_LINE_RE = re.compile(r"^.*\{my_reel_block\}.*\n?", re.MULTILINE)


def compute_confidence(comparison: ComparisonResult) -> Confidence:
    """docs/02-contracts.md confidence 판정표. 모델에 맡기지 않고 코드가 계산한다."""
    if not comparison.sufficient:
        return "불충분"
    if len(comparison.findings) >= CONFIDENCE_SUFFICIENT_MIN_FINDINGS:
        return "충분"
    return "제한적"


def filter_reference_shots(
    shots: list[ShotSegment], constraints: UserConstraints
) -> list[ShotSegment]:
    """docs generating 1번: 사장님이 재현 못 할 기법은 참고 자료에서도 뺀다.

    - shooting_alone=True: requires에 "촬영자"류가 있으면 solo_alternative로 대체,
      대안이 없으면 제외.
    - can_show_face=False: 얼굴이 주 피사체인 샷 제외. VLM이 "얼굴이 주 피사체"를
      별도 필드로 안 주기 때문에 subject 문자열에 "얼굴"이 있는지로 판단한다
      (판단, 문서에 명시된 필드 없음 — 휴리스틱 한계).
    - equipment에 없는 장비를 요구하는 샷 제외.
    """
    filtered: list[ShotSegment] = []
    for shot in shots:
        requires = shot.requires
        solo_substitute: str | None = None

        if constraints.shooting_alone and any("촬영자" in r for r in requires):
            if not shot.solo_alternative:
                continue
            solo_substitute = shot.solo_alternative

        if not constraints.can_show_face and "얼굴" in shot.subject:
            continue

        missing_equipment = [
            r for r in requires if "촬영자" not in r and r not in constraints.equipment
        ]
        if missing_equipment:
            continue

        if solo_substitute is not None:
            shot = shot.model_copy(update={"technique": solo_substitute, "requires": []})
        filtered.append(shot)
    return filtered


def _findings_text(comparison: ComparisonResult) -> str:
    if not comparison.sufficient or not comparison.findings:
        return "표본 부족으로 비교 불가"
    lines = [
        f'- {f.feature}: 상위 "{f.high.value}" {f.high.count}개 중 {f.high.total}개 vs '
        f'하위 "{f.low.value}" {f.low.count}개 중 {f.low.total}개 (차이 {f.gap_pp:.0f}%p)'
        for f in comparison.findings
    ]
    return "\n".join(lines)


def _timing_text(comparison: ComparisonResult) -> str:
    if comparison.timing is None:
        return "데이터 없음"
    t = comparison.timing
    return (
        f"- 첫 컷 길이: 상위 {t.first_shot_sec_high:.1f}초 vs 하위 {t.first_shot_sec_low:.1f}초\n"
        f"- 평균 샷 길이: 상위 {t.avg_shot_sec_high:.1f}초 vs 하위 {t.avg_shot_sec_low:.1f}초\n"
        f"- 컷 수: 상위 {t.cut_count_high:.1f}개 vs 하위 {t.cut_count_low:.1f}개"
    )


def _breakout_shots_text(breakout: list[ReelAnalysis], constraints: UserConstraints) -> str:
    lines: list[str] = []
    for reel in breakout:
        shots = filter_reference_shots(reel.shots, constraints)
        if not shots:
            continue
        lines.append(f"[{reel.reel_code}] {reel.summary}")
        for shot in shots:
            text_part = f" | 자막: {shot.on_screen_text}" if shot.on_screen_text else ""
            lines.append(f"  - {shot.angle} | {shot.subject} | {shot.movement}{text_part}")
    return "\n".join(lines) if lines else "데이터 없음"


def _big_account_context_text(big_account: list[ReelAnalysis]) -> str:
    if not big_account:
        return "데이터 없음"
    lines = [
        f"[{ra.reel_code}] {ra.summary} (캡션 후킹: {', '.join(ra.caption_hooks) or '없음'})"
        for ra in big_account
    ]
    return "\n".join(lines)


def _audio_counts_text(big_account: list[ReelAnalysis]) -> str:
    titles = [ra.audio_title for ra in big_account if ra.audio_title]
    if not titles:
        return "데이터 없음"
    counter = Counter(titles)
    total = len(big_account)
    return "\n".join(f"- {title}: {total}개 중 {count}개" for title, count in counter.most_common())


def _evidence_note_text(comparison: ComparisonResult) -> str:
    if not comparison.sufficient:
        return comparison.insufficient_reason or "표본 부족"
    return (
        f"최근 30일, {comparison.bucket} 구간 상위 {comparison.high_n}개/"
        f"하위 {comparison.low_n}개 기준"
    )


def _my_reel_block_text(my_reel: ReelAnalysis | None, comparison: ComparisonResult) -> str | None:
    """P5(내 릴스 진단). `my_reel`이 없으면 None(호출부가 `{my_reel_block}` 줄 자체를 지운다)."""
    if my_reel is None:
        return None
    if comparison.timing is None:
        benchmark = "벤치마크 없음(표본 부족)"
    else:
        t = comparison.timing
        benchmark = (
            f"컷 수 {t.cut_count_high:.1f}개, 평균 샷 길이 {t.avg_shot_sec_high:.1f}초, "
            f"첫 컷 길이 {t.first_shot_sec_high:.1f}초"
        )
    return (
        "### 내 릴스 진단\n"
        f"내 릴스: 컷 수 {my_reel.cut_count}개, 평균 샷 길이 {my_reel.avg_shot_sec:.1f}초, "
        f"첫 컷 길이 {my_reel.first_shot_sec:.1f}초\n"
        f"돌파형 상위 릴스 평균(벤치마크): {benchmark}"
    )


def render_user_prompt(
    *,
    business_type: str,
    keyword: str,
    comparison: ComparisonResult,
    breakout: list[ReelAnalysis],
    big_account: list[ReelAnalysis],
    constraints: UserConstraints,
    confidence: Confidence,
    my_reel: ReelAnalysis | None = None,
) -> str:
    """prompts/guide_writer.md의 User 템플릿을 채운다.

    .format()을 쓰면 출력 JSON 예시 블록의 중괄호까지 플레이스홀더로 해석돼 깨진다
    (vision_shot.md와 같은 문제) — 단순 문자열 치환으로 우회한다.
    """
    from app.prompts import load_prompt

    template = load_prompt("guide_writer").user_template
    my_reel_block = _my_reel_block_text(my_reel, comparison)
    if my_reel_block is None:
        # "없으면 블록 자체를 넣지 않음"이라는 템플릿 지시대로 줄 전체를 지운다.
        template = _MY_REEL_BLOCK_LINE_RE.sub("", template)
    else:
        template = template.replace("{my_reel_block}", my_reel_block)

    replacements = {
        "{business_type}": business_type,
        "{keyword}": keyword,
        "{shooting_alone}": "예" if constraints.shooting_alone else "아니오",
        "{equipment}": ", ".join(constraints.equipment) or "없음",
        "{space}": constraints.space,
        "{can_show_face}": "예" if constraints.can_show_face else "아니오",
        "{weekly_minutes}": str(constraints.weekly_minutes),
        "{confidence}": confidence,
        "{evidence_note}": _evidence_note_text(comparison),
        "{findings_text}": _findings_text(comparison),
        "{timing_text}": _timing_text(comparison),
        "{breakout_shots}": _breakout_shots_text(breakout, constraints),
        "{big_account_context}": _big_account_context_text(big_account),
        "{audio_counts}": _audio_counts_text(big_account),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)

    return _ARROW_COMMENT_RE.sub("", template).strip()


def _week_of(reference: date) -> date:
    """이번 주 월요일. 명세에 정의 없어 ISO 주 시작(월요일) 관례를 따른 판단."""
    return reference - timedelta(days=reference.weekday())


async def run(job_id: str) -> None:
    from app.providers import get_writer_provider  # 순환 임포트 회피(collect.py와 동일 패턴)

    job = await jobs_db.get_job(UUID(job_id))
    assert job is not None, f"job {job_id} not found"
    keyword = job.request.keyword
    business_type = job.request.business_type
    constraints = job.request.constraints

    comparison = await compare.compute_comparison(keyword, business_type)
    breakout_scored, big_account_scored, _control_scored = await score.compute_tracks(
        keyword, business_type
    )

    breakout: list[ReelAnalysis] = []
    for scored in breakout_scored:
        analysis = await compare.build_reel_analysis(scored, "breakout")
        if analysis is not None:
            breakout.append(analysis)

    big_account: list[ReelAnalysis] = []
    for scored in big_account_scored:
        analysis = await compare.build_reel_analysis(scored, "big_account")
        if analysis is not None:
            big_account.append(analysis)

    confidence = compute_confidence(comparison)

    my_reel: ReelAnalysis | None = None
    my_raw_reel = await reels_db.get_my_reel(keyword, business_type)
    if my_raw_reel is not None:
        my_reel = await compare.build_my_reel_analysis(my_raw_reel.code, my_raw_reel.audio_title)

    provider = get_writer_provider()
    guide = await provider.write_guide(
        business_type=business_type,
        keyword=keyword,
        comparison=comparison,
        breakout=breakout,
        big_account=big_account,
        constraints=constraints,
        confidence=confidence,
        my_reel=my_reel,
    )

    await guides_db.create(
        job_id=UUID(job_id),
        business_type=business_type,
        keyword=keyword,
        week_of=_week_of(datetime.now(UTC).date()),
        guide=guide,
    )
    logger.info(
        "job %s 가이드 생성 완료: confidence=%s, shot_list=%d, caption_drafts=%d",
        job_id,
        guide.confidence,
        len(guide.shot_list),
        len(guide.caption_drafts),
    )
