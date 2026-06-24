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


def extract_frames(
    video_path: str,
    output_dir: str | None = None,
    raw_frame_count: int | None = None,
    width: int = 640,
) -> list[str]:
    """영상 전체 구간에서 균등하게 JPEG 프레임을 추출합니다."""
    ffmpeg_path = _get_ffmpeg_path()
    duration = get_video_duration(video_path)
    raw_frame_count = raw_frame_count or choose_raw_frame_count(duration)
    fps = max(raw_frame_count / max(duration, 1), 0.1)

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="reel_frames_")

    os.makedirs(output_dir, exist_ok=True)
    output_pattern = str(Path(output_dir) / "frame_%03d.jpg")

    subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-i",
            video_path,
            "-vf",
            f"fps={fps},scale={width}:-1",
            "-q:v",
            "4",
            output_pattern,
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
