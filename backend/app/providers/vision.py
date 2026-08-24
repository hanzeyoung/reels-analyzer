import base64
import json
import logging
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel

from app.prompts import load_prompt
from app.providers.base import VisionProvider
from app.schemas.analyze import VisionAnalysis

logger = logging.getLogger(__name__)

# P2 T-2.3 판단(2026-08-14): opus-5 대신 sonnet-5 — 이 호출은 릴스마다(잠재적으로 수백 건)
# 반복되는 배치성 추출 작업이라 비용이 누적된다. sonnet-5도 고해상도 비전(2576px)·structured
# outputs를 지원해 이 작업(구도/자막 OCR 판별, JSON 추출)엔 충분하다고 판단했다.
# T-2.4(G2)에서 Gemini와 비용/지연/스키마 준수율/OCR 정확도를 실측 비교할 때 모델 선택 자체도
# 재검토 대상이다 — 지금은 초기 구현 판단이지 확정이 아니다.
VISION_MODEL = "claude-sonnet-5"
MAX_OUTPUT_TOKENS = 4096

# T-2.4(G2) 판단(2026-08-14): "gemini-2.5-flash" 등 버전 고정 모델은 이 API 키 계정에서
# 404("no longer available to new users")로 막혀 있었다 — 실측으로 확인. 별칭
# "gemini-flash-latest"는 정상 동작 확인(실측). 계정별 모델 가용성이 달라질 수 있는
# 값이라 고정 버전 대신 별칭을 쓴다.
GEMINI_VISION_MODEL = "gemini-flash-latest"


def _gemini_schema(model: type[BaseModel]) -> dict[str, Any]:
    """pydantic 스키마를 Gemini가 받아들이는 형태로 정리한다.

    실측(2026-08-14)으로 확인한 google-genai 2.18.1의 버그: pydantic 모델을
    `response_schema`에 그대로 넘기면, `ConfigDict(extra="forbid")`가 만드는
    `additionalProperties`를 SDK가 `additional_properties`로 잘못 변환해 Gemini API가
    400으로 거부한다("Unknown name additional_properties"). `$defs`/`$ref`로 분리된
    중첩 모델(VisionShotDescription)이 있을 때만 재현됐다 — 단순 모델은 문제없었다.
    우회: additionalProperties/title/$defs를 제거하고 $ref를 직접 인라인한 순수
    dict를 넘긴다(직접 검증함, 정상 동작).
    """

    def strip(node: Any, defs: dict[str, Any]) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_name = node["$ref"].rsplit("/", 1)[-1]
                return strip(defs[ref_name], defs)
            return {
                key: strip(value, defs)
                for key, value in node.items()
                if key not in ("additionalProperties", "title", "$defs")
            }
        if isinstance(node, list):
            return [strip(item, defs) for item in node]
        return node

    raw_schema = model.model_json_schema()
    return strip(raw_schema, raw_schema.get("$defs", {}))  # type: ignore[no-any-return]


class ClaudeVisionProvider(VisionProvider):
    """docs/04-prompts.md → prompts/vision_shot.md 로더 경유. structured outputs로 JSON 강제."""

    def __init__(self, api_key: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key)

    async def analyze_shots(self, frame_paths: list[Path], caption: str) -> VisionAnalysis:
        prompt = load_prompt("vision_shot")
        # .format()을 쓰면 프롬프트 안의 JSON 예시 블록({"shots": [...)의 중괄호까지
        # 플레이스홀더로 해석돼 깨진다 — 단순 문자열 치환으로 우회.
        user_text = prompt.user_template.replace("{cut_count}", str(len(frame_paths))).replace(
            "{caption}", caption
        )

        content: list[dict[str, Any]] = []
        for path in frame_paths:
            image_b64 = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
            content.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64},
                }
            )
        content.append({"type": "text", "text": user_text})

        output_config: dict[str, Any] = {
            "format": {"type": "json_schema", "schema": VisionAnalysis.model_json_schema()},
            "effort": "low",
        }
        messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
        # SDK 타입이 json_schema output_config·이미지+텍스트 혼합 messages를 아직 못 따라온다
        # (anthropic 0.120.2 기준) — 런타임 동작은 정상, mypy 오버로드 매칭만 실패.
        response = await self._client.messages.create(  # type: ignore[call-overload]
            model=VISION_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=prompt.system,
            output_config=output_config,
            messages=messages,
        )
        logger.info(
            "ClaudeVisionProvider 사용량: input_tokens=%d, output_tokens=%d",
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        text = next(block.text for block in response.content if block.type == "text")
        return VisionAnalysis.model_validate_json(text)


class GeminiVisionProvider(VisionProvider):
    """T-2.4(G2): Claude와 실측 비교용. google-genai(신 SDK) 기준."""

    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)

    async def analyze_shots(self, frame_paths: list[Path], caption: str) -> VisionAnalysis:
        prompt = load_prompt("vision_shot")
        user_text = prompt.user_template.replace("{cut_count}", str(len(frame_paths))).replace(
            "{caption}", caption
        )

        parts: list[Any] = [
            genai_types.Part.from_bytes(data=path.read_bytes(), mime_type="image/jpeg")
            for path in frame_paths
        ]
        parts.append(user_text)

        response = await self._client.aio.models.generate_content(
            model=GEMINI_VISION_MODEL,
            contents=parts,
            config=genai_types.GenerateContentConfig(
                system_instruction=prompt.system,
                response_mime_type="application/json",
                response_schema=_gemini_schema(VisionAnalysis),
                # 구도/자막 추출은 깊은 추론이 필요 없는 작업이라 thinking을 꺼서
                # 비용·지연을 줄인다 (Claude 쪽 effort="low"와 같은 취지).
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            ),
        )
        assert response.text is not None
        return VisionAnalysis.model_validate_json(response.text)


class FakeVisionProvider(VisionProvider):
    """fixture는 샷 1개짜리 템플릿만 갖고, 요청받은 frame_paths 개수만큼 복제해서
    돌려준다 — 그래야 analyze.py의 "샷 개수 불일치" 가드에 걸리지 않고 fake 모드로도
    컷 개수 무관하게 전체 파이프라인을 끝까지 돌려볼 수 있다."""

    def __init__(self, fixtures_dir: str) -> None:
        self._fixtures_dir = Path(fixtures_dir)

    async def analyze_shots(self, frame_paths: list[Path], caption: str) -> VisionAnalysis:
        payload = json.loads((self._fixtures_dir / "vision" / "sample.json").read_text())
        template = payload["shots"][0]
        payload["shots"] = [{**template, "index": i} for i in range(len(frame_paths))]
        return VisionAnalysis.model_validate(payload)
