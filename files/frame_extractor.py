"""
app/api/frame_extractor.py
ffmpeg 기반 릴스 프레임 추출 + 중복 제거 모듈
"""

import os
import subprocess
import tempfile
from PIL import Image
import imagehash


# ── 영상 길이 파악 ────────────────────────────

def get_video_duration(video_path: str) -> float:
    """
    ffprobe로 영상 길이(초)를 반환합니다.
    """
    result = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ], capture_output=True, text=True)

    try:
        return float(result.stdout.strip())
    except ValueError:
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
    interval = duration / num_frames

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="reels_frames_")
    os.makedirs(output_dir, exist_ok=True)

    print(f"[frame_extractor] 영상 길이: {duration:.1f}초 → {num_frames}장 추출 (간격: {interval:.1f}초)")

    output_pattern = os.path.join(output_dir, "frame_%03d.jpg")
    subprocess.run([
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"fps=1/{interval}",
        "-q:v", "2",        # JPEG 품질 (1~31, 낮을수록 고품질)
        output_pattern
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
