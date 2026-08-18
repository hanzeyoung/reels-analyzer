from app.config import get_settings
from app.providers.base import CollectProvider, VisionProvider, WriterProvider
from app.providers.collect import ApifyCollectProvider, FakeCollectProvider
from app.providers.vision import ClaudeVisionProvider, FakeVisionProvider
from app.providers.writer import ClaudeWriterProvider, FakeWriterProvider


def get_collect_provider() -> CollectProvider:
    settings = get_settings()
    if settings.apify_mode == "real":
        return ApifyCollectProvider(token=settings.apify_token)
    return FakeCollectProvider(fixtures_dir=settings.fixtures_dir)


def get_vision_provider() -> VisionProvider:
    settings = get_settings()
    if settings.vision_mode == "real":
        return ClaudeVisionProvider(api_key=settings.anthropic_api_key)
    return FakeVisionProvider(fixtures_dir=settings.fixtures_dir)


def get_writer_provider() -> WriterProvider:
    settings = get_settings()
    if settings.writer_mode == "real":
        return ClaudeWriterProvider(api_key=settings.anthropic_api_key)
    return FakeWriterProvider(fixtures_dir=settings.fixtures_dir)


__all__ = [
    "CollectProvider",
    "VisionProvider",
    "WriterProvider",
    "get_collect_provider",
    "get_vision_provider",
    "get_writer_provider",
]
