"""Deterministic full-video signals for pacing and drop-off risk analysis."""

from __future__ import annotations

import math
import subprocess
import tempfile
import wave
from pathlib import Path

try:
    import cv2
except ImportError:
    cv2 = None
import numpy as np

from app.core.frame_extractor import _get_ffmpeg_path, get_video_duration


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(float(value), high))


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    high = float(np.percentile(values, 95))
    if high <= 0:
        return [0.0 for _ in values]
    return [round(_clamp(value / high, 0, 1), 4) for value in values]


def extract_visual_samples(video_path: str, sample_fps: float = 2.0, max_duration: float = 180.0) -> list[dict]:
    """Sample the whole video and measure visual change instead of inspecting only a few frames."""
    if cv2 is None:
        raise RuntimeError("영상 타임라인 분석에는 OpenCV 설치가 필요합니다.")
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"영상을 열 수 없습니다: {video_path}")

    native_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = min(frame_count / native_fps if frame_count else get_video_duration(video_path), max_duration)
    step = 1.0 / max(sample_fps, 0.5)
    timestamps = np.arange(0.0, max(duration, step), step)
    samples = []
    previous = None

    for timestamp in timestamps:
        capture.set(cv2.CAP_PROP_POS_MSEC, float(timestamp) * 1000)
        ok, frame = capture.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (160, 90), interpolation=cv2.INTER_AREA)
        motion = 0.0 if previous is None else float(np.mean(cv2.absdiff(gray, previous))) / 255.0
        samples.append({
            "timestamp_seconds": round(float(timestamp), 2),
            "motion_raw": motion,
            "brightness": round(float(np.mean(gray)) / 255.0, 4),
        })
        previous = gray

    capture.release()
    motions = _normalize([sample["motion_raw"] for sample in samples])
    for sample, motion in zip(samples, motions):
        sample["motion"] = motion
        sample.pop("motion_raw", None)
    return samples


def extract_audio_energy(video_path: str, duration: float) -> list[float]:
    """Decode audio to mono PCM and return normalized RMS energy for each second."""
    ffmpeg = _get_ffmpeg_path()
    with tempfile.TemporaryDirectory(prefix="reel_audio_") as directory:
        wav_path = Path(directory) / "audio.wav"
        result = subprocess.run(
            [ffmpeg, "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", str(wav_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        if result.returncode != 0 or not wav_path.exists():
            return [0.0] * max(1, math.ceil(duration))

        with wave.open(str(wav_path), "rb") as wav:
            rate = wav.getframerate()
            width = wav.getsampwidth()
            frames = wav.readframes(wav.getnframes())
        if width != 2 or not frames:
            return [0.0] * max(1, math.ceil(duration))
        pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        values = []
        for start in range(0, len(pcm), rate):
            chunk = pcm[start:start + rate]
            values.append(float(np.sqrt(np.mean(np.square(chunk)))) if len(chunk) else 0.0)
        return _normalize(values)


def build_signal_timeline(visual_samples: list[dict], audio_energy: list[float], duration: float) -> dict:
    """Convert measured signals into explainable risks and a heuristic retention curve."""
    second_count = max(1, math.ceil(duration))
    buckets = []
    for second in range(second_count):
        visual = [
            sample for sample in visual_samples
            if second <= sample["timestamp_seconds"] < second + 1
        ]
        motion = float(np.mean([sample["motion"] for sample in visual])) if visual else 0.0
        brightness = float(np.mean([sample["brightness"] for sample in visual])) if visual else 0.0
        audio = audio_energy[second] if second < len(audio_energy) else 0.0
        buckets.append({
            "timestamp_seconds": float(second),
            "motion": round(motion, 3),
            "audio_energy": round(audio, 3),
            "brightness": round(brightness, 3),
        })

    motion_values = [item["motion"] for item in buckets]
    cut_threshold = max(0.45, float(np.percentile(motion_values, 80)) if motion_values else 0.45)
    for item in buckets:
        item["cut_signal"] = item["motion"] >= cut_threshold

    diagnostics = []
    low_run_start = None
    for index, item in enumerate(buckets + [{"motion": 1.0, "audio_energy": 1.0}]):
        stagnant = item["motion"] < 0.12 and item["audio_energy"] < 0.18
        if stagnant and low_run_start is None:
            low_run_start = index
        if not stagnant and low_run_start is not None:
            run_length = index - low_run_start
            if run_length >= 2:
                diagnostics.append({
                    "timestamp_seconds": float(low_run_start),
                    "end_seconds": float(index),
                    "kind": "risk",
                    "title": "화면과 소리가 함께 정체되는 구간",
                    "reason": f"약 {run_length}초 동안 장면 변화와 오디오 에너지가 모두 낮게 측정됐습니다.",
                    "confidence": "high",
                    "action": "이 구간을 줄이거나 새 화면, 손동작, 자막 변화를 넣으세요.",
                    "evidence": "measured_video_audio",
                })
            low_run_start = None

    intro = buckets[: min(3, len(buckets))]
    intro_motion = float(np.mean([item["motion"] for item in intro])) if intro else 0.0
    intro_cuts = sum(1 for item in intro if item["cut_signal"])
    if intro_motion < 0.16 and intro_cuts == 0:
        diagnostics.insert(0, {
            "timestamp_seconds": 0.0,
            "end_seconds": min(3.0, duration),
            "kind": "risk",
            "title": "초반 시각 변화가 약함",
            "reason": "첫 3초의 움직임과 장면 전환이 낮게 측정됐습니다.",
            "confidence": "high",
            "action": "첫 1초에 결과 장면을 배치하고 3초 안에 한 번 이상 화면을 전환하세요.",
            "evidence": "measured_video",
        })
    elif intro_motion >= 0.3 or intro_cuts >= 1:
        diagnostics.insert(0, {
            "timestamp_seconds": 0.0,
            "end_seconds": min(3.0, duration),
            "kind": "strength",
            "title": "초반 변화량이 충분함",
            "reason": "첫 3초에 움직임 또는 장면 전환 신호가 확인됐습니다.",
            "confidence": "medium",
            "action": "핵심 메뉴와 문구가 동시에 명확한지만 확인하세요.",
            "evidence": "measured_video",
        })

    retention = 100.0
    curve = []
    risk_seconds = set()
    for diagnostic in diagnostics:
        if diagnostic["kind"] == "risk":
            start = int(diagnostic["timestamp_seconds"])
            end = int(math.ceil(diagnostic.get("end_seconds", start + 1)))
            risk_seconds.update(range(start, end))
    for item in buckets:
        second = int(item["timestamp_seconds"])
        decay = 0.8
        if second in risk_seconds:
            decay += 3.5
        if item["motion"] < 0.08:
            decay += 0.7
        if item["audio_energy"] < 0.08:
            decay += 0.5
        if item["cut_signal"]:
            decay -= 0.4
        retention = _clamp(retention - max(decay, 0.25), 5, 100)
        curve.append({**item, "predicted_retention": round(retention, 1)})

    return {
        "duration_seconds": round(duration, 2),
        "sample_count": len(visual_samples),
        "timeline_signals": curve,
        "timeline_diagnostics": diagnostics,
        "signal_summary": {
            "cuts_detected": sum(1 for item in buckets if item["cut_signal"]),
            "average_motion": round(float(np.mean(motion_values)) if motion_values else 0.0, 3),
            "average_audio_energy": round(float(np.mean(audio_energy)) if audio_energy else 0.0, 3),
        },
        "analysis_basis": "measured full-video motion and audio signals; retention is heuristic",
    }


def analyze_video_timeline(video_path: str) -> dict:
    duration = min(get_video_duration(video_path), 180.0)
    visual = extract_visual_samples(video_path)
    audio = extract_audio_energy(video_path, duration)
    return build_signal_timeline(visual, audio, duration)
