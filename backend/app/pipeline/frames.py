"""JobStage 'preparing'. docs/03-pipeline.md의 preparing 참조 (P2, 2026-08-14 정정본).

mp4 다운로드 + ffmpeg scene detect + 컷별 대표 프레임 추출 + phash 중복 제거.
`shot_segments`에 t_start/t_end/idx만 먼저 커밋한다 — VLM 필드는 analyzing이 채운다.
"""

import asyncio
import logging
import re
import tempfile
from pathlib import Path
from uuid import UUID

import httpx
from PIL import Image

from app.config import get_settings
from app.db import jobs as jobs_db
from app.db import shot_segments as shot_segments_db
from app.pipeline.score import select_target_reels
from app.schemas.collect import RawReel
from app.schemas.frames import Cut

logger = logging.getLogger(__name__)

MIN_CUTS = 3  # docs preparing 3번: 미만이면 균등分할로 폴백
FALLBACK_SPLITS = 5
MAX_FRAMES = 12  # docs preparing 5번: phash 중복 제거 후 상한
# 64비트 phash 기준 "사실상 동일 프레임" 판정 임계값 — 문서에 숫자가 없어 판단한 값.
PHASH_HAMMING_THRESHOLD = 5

_PTS_TIME_RE = re.compile(r"pts_time:([\d.]+)")


def _parse_scene_change_times(ffmpeg_stderr: str) -> list[float]:
    """`-vf "select='gt(scene,X)',showinfo"` 출력에서 pts_time을 뽑는다."""
    return [float(m.group(1)) for m in _PTS_TIME_RE.finditer(ffmpeg_stderr)]


def build_cut_boundaries(scene_times: list[float], duration: float) -> list[tuple[float, float]]:
    """scene 경계 시각들로 (t_start, t_end) 구간 리스트를 만든다.

    구간이 3개 미만이면(docs preparing 3번) 균등 5분할로 폴백한다(단일 컷 롱테이크 대응).
    """
    boundaries = sorted({t for t in scene_times if 0 < t < duration})
    points = [0.0, *boundaries, duration]
    segments = [
        (points[i], points[i + 1])
        for i in range(len(points) - 1)
        if points[i] < points[i + 1]
    ]

    if len(segments) < MIN_CUTS:
        step = duration / FALLBACK_SPLITS
        segments = [(i * step, (i + 1) * step) for i in range(FALLBACK_SPLITS)]

    return segments


async def _ffprobe_duration(video_path: Path) -> float:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return float(stdout.decode().strip())


async def _run_scene_detect(video_path: Path, threshold: float) -> list[float]:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", str(video_path),
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    return _parse_scene_change_times(stderr.decode(errors="ignore"))


async def _extract_representative_frames(
    video_path: Path, segments: list[tuple[float, float]], frame_dir: Path
) -> list[Cut]:
    """컷 중앙 지점에서 대표 프레임 1장씩 추출한다 (docs preparing 4번)."""
    cuts: list[Cut] = []
    for index, (t_start, t_end) in enumerate(segments):
        mid = (t_start + t_end) / 2
        frame_path = frame_dir / f"frame_{index:02d}.jpg"
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-ss", f"{mid:.3f}", "-i", str(video_path),
            "-frames:v", "1", "-q:v", "2", str(frame_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if frame_path.exists():
            cuts.append(Cut(index=index, t_start=t_start, t_end=t_end, frame_path=str(frame_path)))
    return cuts


def dedupe_by_phash(
    cuts: list[Cut], *, threshold: int = PHASH_HAMMING_THRESHOLD, max_frames: int = MAX_FRAMES
) -> list[Cut]:
    """phash 해밍 거리 기준 유사 프레임 제거 후 최대 max_frames장으로 자른다."""
    import imagehash

    kept: list[Cut] = []
    kept_hashes: list[imagehash.ImageHash] = []
    for cut in cuts:
        h = imagehash.phash(Image.open(cut.frame_path))
        if any((h - kh) <= threshold for kh in kept_hashes):
            continue
        kept.append(cut)
        kept_hashes.append(h)
    return kept[:max_frames]


async def _process_reel(reel: RawReel, job_id: str) -> None:
    if await shot_segments_db.has_any(reel.code):
        logger.info("릴스 %s는 이미 shot_segments 있음 — 다운로드 건너뜀", reel.code)
        return
    if not reel.video_url:
        logger.warning("릴스 %s는 video_url이 없어 다운로드 불가 — 스킵", reel.code)
        return

    settings = get_settings()
    workdir = Path(tempfile.gettempdir()) / "buja_frames" / job_id / reel.code
    workdir.mkdir(parents=True, exist_ok=True)
    video_path = workdir / "source.mp4"

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        async with client.stream("GET", reel.video_url) as response:
            response.raise_for_status()
            with open(video_path, "wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)

    duration = await _ffprobe_duration(video_path)
    scene_times = await _run_scene_detect(video_path, settings.scene_detect_threshold)
    segments = build_cut_boundaries(scene_times, duration)
    cuts = await _extract_representative_frames(video_path, segments, workdir)
    cuts = dedupe_by_phash(cuts)

    await shot_segments_db.insert_cut_timings(reel.code, cuts)
    # mp4는 여기서 지우지 않는다 — docs/03-pipeline.md analyzing 4번이 VLM 호출 후
    # 삭제하는 것으로 명시돼 있다. frame 이미지도 analyzing이 다 쓴 뒤에야 필요 없어진다.


async def run(job_id: str) -> None:
    job = await jobs_db.get_job(UUID(job_id))
    assert job is not None, f"job {job_id} not found"
    keyword = job.request.keyword
    business_type = job.request.business_type

    targets = await select_target_reels(keyword, business_type)
    logger.info("job %s preparing 대상 %d개", job_id, len(targets))

    for reel in targets:
        try:
            await _process_reel(reel, job_id)
        except Exception:  # noqa: BLE001 — 릴스 1개 실패가 전체를 막으면 안 된다 (docs 실패 원칙)
            logger.exception("릴스 %s 처리 실패 — 로그만 남기고 계속", reel.code)
