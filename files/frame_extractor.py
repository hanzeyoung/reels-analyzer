"""
app/api/frame_extractor.py
ffmpeg 기반 릴스 프레임 추출 + 중복 제거 모듈
"""

import os
import re
import shutil
import subprocess
import tempfile
from PIL import Image
import imagehash


def _get_ffmpeg_cmd() -> str:
    """
    시스템 ffmpeg이 없으면 imageio-ffmpeg 패키지의 번들 바이너리를 사용합니다.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError(
            "[frame_extractor] ffmpeg을 찾을 수 없습니다. "
            "ffmpeg을 설치하거나 imageio-ffmpeg 패키지를 설치하세요."
        ) from exc


def _get_ffprobe_cmd() -> str | None:
    return shutil.which("ffprobe")


# ── 영상 길이 파악 ────────────────────────────

def get_video_duration(video_path: str) -> float:
    """
    ffprobe 또는 ffmpeg로 영상 길이(초)를 반환합니다.
    """
    ffprobe = _get_ffprobe_cmd()
    if ffprobe:
        result = subprocess.run([
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ], capture_output=True, text=True)

        try:
            return float(result.stdout.strip())
        except ValueError:
            pass

    ffmpeg = _get_ffmpeg_cmd()
    result = subprocess.run([
        ffmpeg, "-i", video_path
    ], capture_output=True, text=True)
    duration_match = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
        result.stderr,
    )
    if duration_match:
        hours, minutes, seconds = duration_match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    raise RuntimeError(f"[frame_extractor] 영상 길이 파악 실패: {video_path}")


# ── 영상 길이에 따라 프레임 수 결정 ──────────

def _decide_num_frames(duration: float) -> int:
    """
    영상 길이에 비례해서 추출할 프레임 수를 결정합니다.
    짧은 영상은 적게, 긴 영상은 많이.
    """
    if duration <= 15:
        return 5
    elif duration <= 30:
        return 7
    elif duration <= 60:
        return 10
    else:
        return 12


def _split_frame_counts(total: int) -> tuple[int, int, int]:
    """
    초반/중반/후반 프레임 수를 나눕니다.
    릴스 후킹 분석을 위해 초반에 약 60%를 배정합니다.
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


def _evenly_spaced_times(start: float, end: float, count: int, duration: float) -> list[float]:
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


def _build_weighted_timestamps(duration: float, total: int) -> list[float]:
    """
    초반/중반/후반으로 나누되 초반을 더 촘촘히 뽑습니다.
    - 초반: 0~20%
    - 중반: 20~70%
    - 후반: 70~100%
    """
    intro_count, middle_count, ending_count = _split_frame_counts(total)
    intro_end = min(duration * 0.20, 4.0)
    middle_end = duration * 0.70

    timestamps = []
    timestamps.extend(_evenly_spaced_times(0.0, intro_end, intro_count, duration))
    timestamps.extend(_evenly_spaced_times(intro_end, middle_end, middle_count, duration))
    timestamps.extend(_evenly_spaced_times(middle_end, duration, ending_count, duration))
    return sorted(set(round(ts, 2) for ts in timestamps))


# ── 중복 프레임 제거 ──────────────────────────

def _remove_similar_frames(frame_paths: list[str], threshold: int = 8) -> list[str]:
    """
    perceptual hash로 비슷한 프레임을 제거합니다.
    threshold: 낮을수록 엄격하게 제거 (기본값 8 권장)
    """
    if not frame_paths:
        return []

    unique = [frame_paths[0]]

    for path in frame_paths[1:]:
        prev_hash = imagehash.phash(Image.open(unique[-1]))
        curr_hash = imagehash.phash(Image.open(path))

        if (prev_hash - curr_hash) > threshold:
            unique.append(path)
        else:
            print(f"[frame_extractor] 중복 제거: {os.path.basename(path)}")

    return unique


# ── 메인 함수 ─────────────────────────────────

def extract_frames(
    video_path: str,
    output_dir: str = None,
    deduplicate: bool = True,
    threshold: int = 8,
) -> list[str]:
    """
    릴스 영상에서 프레임을 추출합니다.
    영상 길이에 따라 자동으로 프레임 수를 결정하고,
    초반/중반/후반 중 초반 후킹 구간을 더 촘촘히 추출한 뒤
    중복 프레임을 제거합니다.

    Args:
        video_path: 입력 영상 경로
        output_dir: 프레임 저장 디렉토리 (None이면 임시 폴더 생성)
        deduplicate: 중복 제거 여부 (기본 True)
        threshold: 중복 판단 민감도 (낮을수록 엄격)

    Returns:
        최종 프레임 파일 경로 리스트
    """
    duration = get_video_duration(video_path)
    num_frames = _decide_num_frames(duration)
    timestamps = _build_weighted_timestamps(duration, num_frames)

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="reels_frames_")
    os.makedirs(output_dir, exist_ok=True)
    for filename in os.listdir(output_dir):
        if filename.startswith("frame_") and filename.endswith(".jpg"):
            os.remove(os.path.join(output_dir, filename))

    intro_count, middle_count, ending_count = _split_frame_counts(num_frames)
    print(
        f"[frame_extractor] 영상 길이: {duration:.1f}초 → {num_frames}장 추출 "
        f"(초반 {intro_count}, 중반 {middle_count}, 후반 {ending_count})"
    )

    ffmpeg = _get_ffmpeg_cmd()

    for idx, timestamp in enumerate(timestamps, start=1):
        output_path = os.path.join(output_dir, f"frame_{idx:03d}_{timestamp:05.2f}s.jpg")
        subprocess.run([
            ffmpeg, "-y",
            "-ss", f"{timestamp:.2f}",
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "2",        # JPEG 품질 (1~31, 낮을수록 고품질)
            output_path,
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    frames = sorted([
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.endswith(".jpg")
    ])

    print(f"[frame_extractor] 추출 완료: {len(frames)}장")

    if deduplicate:
        frames = _remove_similar_frames(frames, threshold)
        print(f"[frame_extractor] 중복 제거 후: {len(frames)}장")

    return frames


# ── 임시 파일 정리 ────────────────────────────

def cleanup_frames(frame_paths: list[str]):
    """
    추출된 임시 프레임 파일을 삭제합니다.
    """
    for path in frame_paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

    # 빈 디렉토리도 삭제
    if frame_paths:
        dir_path = os.path.dirname(frame_paths[0])
        try:
            os.rmdir(dir_path)
        except OSError:
            pass
