"""
core/frame_extractor.py
릴스 영상에서 분석용 프레임을 추출하고, 너무 비슷한 프레임을 제거합니다.
"""

import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image
import imagehash


def _get_ffmpeg_path() -> str:
    """PATH의 ffmpeg 또는 imageio-ffmpeg가 제공하는 ffmpeg 경로를 반환합니다."""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        raise RuntimeError(
            "ffmpeg을 찾을 수 없습니다. PATH에 ffmpeg을 설치하거나 imageio-ffmpeg를 설치하세요."
        ) from e


def get_video_duration(video_path: str) -> float:
    """ffmpeg 출력에서 영상 길이(초)를 추출합니다."""
    ffmpeg_path = _get_ffmpeg_path()
    result = subprocess.run(
        [ffmpeg_path, "-i", video_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )

    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if not match:
        raise RuntimeError(f"영상 길이를 읽을 수 없습니다: {video_path}")

    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def choose_raw_frame_count(duration: float) -> int:
    """
    영상 길이에 따라 넉넉하게 프레임을 뽑습니다.
    짧은 릴스의 빠른 컷을 놓치지 않되, 이후 중복 제거로 토큰 낭비를 줄입니다.
    """
    if duration <= 10:
        return 10
    if duration <= 20:
        return 12
    if duration <= 40:
        return 14
    if duration <= 60:
        return 16
    return 18


def split_frame_counts(total: int) -> tuple[int, int, int]:
    """
    초반/중반/후반 프레임 수를 나눕니다.
    릴스 후킹 분석을 위해 초반 구간에 약 60%를 배정합니다.
    """
    intro = max(1, round(total * 0.60))
    middle = max(1, round(total * 0.25))
    ending = max(1, total - intro - middle)

    while intro + middle + ending > total:
        if middle >= ending and middle > 1:
            middle -= 1
        elif ending > 1:
            ending -= 1
        else:
            intro -= 1

    while intro + middle + ending < total:
        intro += 1

    return intro, middle, ending


def evenly_spaced_times(start: float, end: float, count: int, duration: float) -> list[float]:
    if count <= 0:
        return []

    start = max(0.0, min(start, duration))
    end = max(start, min(end, duration))
    if end <= start:
        return [min(start, max(duration - 0.05, 0.0))]

    step = (end - start) / count
    return [
        min(start + step * (idx + 0.5), max(duration - 0.05, 0.0))
        for idx in range(count)
    ]


def build_weighted_timestamps(duration: float, total: int) -> list[float]:
    """
    초반/중반/후반으로 나누되 초반 후킹 구간을 더 촘촘히 뽑습니다.
    - 초반: 0~20%
    - 중반: 20~70%
    - 후반: 70~100%
    """
    intro_count, middle_count, ending_count = split_frame_counts(total)
    intro_end = min(duration * 0.20, 4.0)
    middle_end = duration * 0.70

    timestamps = []
    timestamps.extend(evenly_spaced_times(0.0, intro_end, intro_count, duration))
    timestamps.extend(evenly_spaced_times(intro_end, middle_end, middle_count, duration))
    timestamps.extend(evenly_spaced_times(middle_end, duration, ending_count, duration))
    return sorted(set(round(ts, 2) for ts in timestamps))


def extract_frames(
    video_path: str,
    output_dir: str | None = None,
    raw_frame_count: int | None = None,
    width: int = 640,
) -> list[str]:
    """초반 후킹 구간을 더 촘촘히 보도록 가중 샘플링해서 JPEG 프레임을 추출합니다."""
    ffmpeg_path = _get_ffmpeg_path()
    duration = get_video_duration(video_path)
    raw_frame_count = raw_frame_count or choose_raw_frame_count(duration)
    timestamps = build_weighted_timestamps(duration, raw_frame_count)

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="reel_frames_")

    os.makedirs(output_dir, exist_ok=True)
    for path in Path(output_dir).glob("frame_*.jpg"):
        path.unlink()

    for idx, timestamp in enumerate(timestamps, start=1):
        output_path = str(Path(output_dir) / f"frame_{idx:03d}_{timestamp:05.2f}s.jpg")
        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-ss",
                f"{timestamp:.2f}",
                "-i",
                video_path,
                "-frames:v",
                "1",
                "-vf",
                f"scale={width}:-1",
                "-q:v",
                "4",
                output_path,
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )

    return sorted(str(path) for path in Path(output_dir).glob("frame_*.jpg"))


def remove_similar_frames(
    frame_paths: list[str],
    hash_threshold: int = 8,
    max_frames: int = 8,
) -> list[str]:
    """
    perceptual hash로 너무 비슷한 프레임을 제거합니다.
    hash_threshold가 낮을수록 더 엄격하게 중복으로 봅니다.
    """
    unique_paths = []
    unique_hashes = []

    for frame_path in frame_paths:
        image_hash = imagehash.phash(Image.open(frame_path))

        if all(image_hash - prev_hash > hash_threshold for prev_hash in unique_hashes):
            unique_paths.append(frame_path)
            unique_hashes.append(image_hash)

        if len(unique_paths) >= max_frames:
            break

    return unique_paths


def extract_unique_frames(
    video_path: str,
    output_dir: str | None = None,
    max_frames: int = 8,
    hash_threshold: int = 8,
) -> list[str]:
    """프레임을 넉넉히 추출한 뒤 유사 프레임을 제거합니다."""
    duration = get_video_duration(video_path)
    raw_frame_count = max(choose_raw_frame_count(duration), math.ceil(max_frames * 1.8))
    frames = extract_frames(video_path, output_dir=output_dir, raw_frame_count=raw_frame_count)

    if not frames:
        return []

    unique_frames = remove_similar_frames(
        frames,
        hash_threshold=hash_threshold,
        max_frames=max_frames,
    )
    return unique_frames or frames[:max_frames]
