"""backend/prompts/*.md 로더. docs/04-prompts.md가 원본이고 backend/prompts/*.md는
그 사본이다(항상 같이 바꾼다). 프롬프트를 코드에 하드코딩하지 않기 위한 유일한 경로."""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

_SECTION_HEADER_RE = re.compile(r"^##\s+(System|User)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class PromptTemplate:
    system: str
    user_template: str


@lru_cache
def load_prompt(name: str) -> PromptTemplate:
    """`name`은 확장자 없는 파일명. 예: 'vision_shot', 'guide_writer'."""
    path = PROMPTS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    sections = _split_sections(text)
    return PromptTemplate(system=sections["System"], user_template=sections["User"])


def _split_sections(text: str) -> dict[str, str]:
    matches = list(_SECTION_HEADER_RE.finditer(text))
    if len(matches) != 2 or {m.group(1) for m in matches} != {"System", "User"}:
        raise ValueError(
            "프롬프트 파일에는 '## System'과 '## User' 섹션이 정확히 하나씩 있어야 한다"
        )
    result: dict[str, str] = {}
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        result[match.group(1)] = _strip_fence(text[start:end].strip())
    return result


def _strip_fence(block: str) -> str:
    lines = block.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
