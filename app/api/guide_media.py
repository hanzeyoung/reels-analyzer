"""Server-side guide image and optional voiceover generation."""

from __future__ import annotations

import time
from pathlib import Path

import requests

from app.core.config import get_env, require_env


def generate_flux_guide(prompt: str, aspect_ratio: str = "9:16") -> dict:
    """Generate a storyboard reference image through the configured BFL account."""
    key = require_env("BFL_API_KEY", "Flux 가이드 이미지 생성")
    endpoint = get_env("BFL_FLUX_ENDPOINT", "https://api.bfl.ai/v1/flux-pro-1.1")
    response = requests.post(
        endpoint,
        headers={"x-key": key, "Content-Type": "application/json"},
        # FLUX1.1 [pro] takes dimensions, rather than an aspect_ratio parameter.
        # 768 x 1376 is within its supported range and close to vertical 9:16.
        json={"prompt": prompt[:2000], "width": 768, "height": 1376, "output_format": "jpeg"},
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    polling_url = payload.get("polling_url")
    if not polling_url:
        raise RuntimeError("Flux 응답에 polling_url이 없습니다.")
    for _ in range(40):
        result = requests.get(polling_url, headers={"x-key": key}, timeout=30)
        result.raise_for_status()
        completed = result.json()
        if completed.get("status") == "Ready":
            sample = (completed.get("result") or {}).get("sample")
            if not sample:
                raise RuntimeError("Flux 결과 이미지 URL이 없습니다.")
            return {"sample_url": sample, "provider": "bfl_flux", "prompt": prompt, "aspect_ratio": aspect_ratio}
        if completed.get("status") in {"Error", "Failed", "Content Moderated"}:
            raise RuntimeError(f"Flux 생성 실패: {completed.get('status')}")
        time.sleep(1.5)
    raise TimeoutError("Flux 가이드 이미지 생성 시간이 초과됐습니다.")


def download_flux_guide(sample_url: str, target: str | Path) -> str:
    """Cache BFL's short-lived delivery URL in the user's project folder."""
    response = requests.get(sample_url, timeout=60)
    response.raise_for_status()
    destination = Path(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)
    return str(destination)


def generate_elevenlabs_voiceover(text: str, voice_id: str = "") -> bytes:
    """Return MP3 bytes. The API key is never sent to the browser."""
    key = require_env("ELEVENLABS_API_KEY", "음성 가이드 생성")
    voice = voice_id or require_env("ELEVENLABS_VOICE_ID", "음성 가이드 생성")
    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        params={"output_format": "mp3_44100_128"},
        json={"text": text[:5000], "model_id": get_env("ELEVENLABS_MODEL", "eleven_multilingual_v2")},
        timeout=90,
    )
    response.raise_for_status()
    return response.content
