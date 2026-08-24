import json
import logging
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from app.pipeline.guide import render_user_prompt
from app.prompts import load_prompt
from app.providers.base import WriterProvider
from app.schemas.analyze import ReelAnalysis
from app.schemas.common import Confidence
from app.schemas.compare import ComparisonResult
from app.schemas.guide import Guide
from app.schemas.requests import UserConstraints

logger = logging.getLogger(__name__)

# P4 판단(2026-08-14): vision과 같은 이유로 sonnet-5 — 이 호출도 잡 1건당 1회지만
# 반복 실행되는 배치성 작업이라 opus 대신 비용 효율 우선. 필요하면 나중에 품질 보고 올린다.
WRITER_MODEL = "claude-sonnet-5"
MAX_OUTPUT_TOKENS = 4096
# docs/03-pipeline.md generating 3번: "반환 JSON을 Guide로 검증. 실패 시 1회 재시도".
MAX_RETRIES = 1


class ClaudeWriterProvider(WriterProvider):
    """프롬프트는 docs/04-prompts.md → prompts/guide_writer.md 로더 경유.
    structured outputs(json_schema)로 Guide 스키마를 강제한다."""

    def __init__(self, api_key: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key)

    async def write_guide(
        self,
        *,
        business_type: str,
        keyword: str,
        comparison: ComparisonResult,
        breakout: list[ReelAnalysis],
        big_account: list[ReelAnalysis],
        constraints: UserConstraints,
        confidence: Confidence,
        my_reel: ReelAnalysis | None = None,
    ) -> Guide:
        prompt = load_prompt("guide_writer")
        user_text = render_user_prompt(
            business_type=business_type,
            keyword=keyword,
            comparison=comparison,
            breakout=breakout,
            big_account=big_account,
            constraints=constraints,
            confidence=confidence,
            my_reel=my_reel,
        )

        last_error: Exception | None = None
        for _attempt in range(MAX_RETRIES + 1):
            output_config: dict[str, Any] = {
                "format": {"type": "json_schema", "schema": Guide.model_json_schema()},
                "effort": "low",
            }
            messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]
            response = await self._client.messages.create(  # type: ignore[call-overload]
                model=WRITER_MODEL,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=prompt.system,
                output_config=output_config,
                messages=messages,
            )
            logger.info(
                "ClaudeWriterProvider 사용량: input_tokens=%d, output_tokens=%d",
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            text = next(block.text for block in response.content if block.type == "text")
            try:
                guide = Guide.model_validate_json(text)
            except Exception as exc:  # noqa: BLE001 — 스키마 검증 실패 시 1회 재시도(docs)
                last_error = exc
                continue
            # confidence는 코드가 계산한 값으로 항상 덮어쓴다(docs — 모델 출력 무시).
            return guide.model_copy(update={"confidence": confidence})

        assert last_error is not None
        raise last_error


class FakeWriterProvider(WriterProvider):
    def __init__(self, fixtures_dir: str) -> None:
        self._fixtures_dir = Path(fixtures_dir)

    async def write_guide(
        self,
        *,
        business_type: str,
        keyword: str,
        comparison: ComparisonResult,
        breakout: list[ReelAnalysis],
        big_account: list[ReelAnalysis],
        constraints: UserConstraints,
        confidence: Confidence,
        my_reel: ReelAnalysis | None = None,
    ) -> Guide:
        payload = json.loads((self._fixtures_dir / "writer" / "sample.json").read_text())
        guide = Guide.model_validate(payload)
        # confidence는 코드가 덮어쓴다 (docs/04-prompts.md 스키마 준수 처리 참조).
        return guide.model_copy(update={"confidence": confidence})
