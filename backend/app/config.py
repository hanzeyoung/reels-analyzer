from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_FIXTURES_DIR = str(_PROJECT_ROOT / "fixtures")


class Settings(BaseSettings):
    # .env는 backend/가 아니라 프로젝트 루트에 있다 (CLAUDE.md 디렉토리 구조).
    # cwd 기준 상대경로("./.env")로 두면 Makefile이 `cd backend &&`로 실행할 때
    # 못 찾는다 — 절대경로로 고정한다.
    model_config = SettingsConfigDict(env_file=str(_PROJECT_ROOT / ".env"), extra="ignore")

    database_url: str = ""

    apify_mode: str = "fake"
    vision_mode: str = "fake"
    writer_mode: str = "fake"

    apify_token: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    stale_minutes: int = 5
    # 프로젝트 루트 기준 절대경로가 기본값. cwd에 따라 깨지지 않는다 (G0 D).
    fixtures_dir: str = _DEFAULT_FIXTURES_DIR

    # docs/03-pipeline.md preparing 2번: "임계값은 설정값으로 뺀다". ffmpeg scene detect의
    # `gt(scene,X)` 민감도 — 낮을수록 컷을 더 많이 잡는다. 문서 예시값 0.3을 기본값으로.
    scene_detect_threshold: float = 0.3


@lru_cache
def get_settings() -> Settings:
    return Settings()
