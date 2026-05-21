"""
api/report_writer.py
Claude API — 분석 인사이트를 소상공인 친화적 보고서로 작성

Gemini가 눈 역할 (영상 분석),
Python이 두뇌 역할 (패턴 집계/비교),
Claude가 입 역할 (보고서 자연어 작성).
"""

import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-opus-4-5"


# ── 시스템 프롬프트 ──────────────────────────

SYSTEM_PROMPT = """
당신은 소상공인 인스타그램 마케팅 전문 컨설턴트입니다.
데이터 분석 결과를 받아, 자영업자가 내일 당장 촬영에 적용할 수 있도록
쉽고 실용적인 언어로 보고서를 작성합니다.

보고서 작성 원칙:
- 전문 용어 대신 일상 언어 사용
- 추상적인 말 금지 ("더 나은 콘텐츠" X → "탑뷰로 찍고 첫 3초에 음식 클로즈업" O)
- 각 포인트는 2줄 이내로 간결하게
- 긍정적이고 실행 가능한 톤 유지
- 마크다운 형식으로 작성 (헤더, 볼드, 리스트 사용)
"""


# ── 보고서 생성 ──────────────────────────────

def generate_report(report_input: dict) -> str:
    """
    build_report_input()의 결과를 받아 Claude가 보고서를 작성합니다.

    Args:
        report_input: video_analyzer.build_report_input() 반환값

    Returns:
        마크다운 형식의 보고서 문자열
    """
    btype = report_input.get("business_type", "소상공인")
    total = report_input.get("total_analyzed", 0)
    top_count = report_input.get("top_count", 0)
    top_common = report_input.get("top_common", {})
    differences = report_input.get("key_differences", [])
    summaries = report_input.get("individual_summaries", [])

    user_prompt = f"""
다음은 인스타그램 릴스 분석 결과입니다. 업종은 '{btype}'입니다.

## 분석 개요
- 총 분석 영상 수: {total}개
- 상위(S/A급) 릴스: {top_count}개

## 상위 릴스 공통 패턴
{json.dumps(top_common, ensure_ascii=False, indent=2)}

## 상위 vs 하위 핵심 차이점
{chr(10).join(f"- {d}" for d in differences)}

## 상위 릴스 개별 요약
{chr(10).join(f"- [{s['tier']}] {s['reel_id']}: {s['summary']}" for s in summaries[:5])}

---
위 데이터를 바탕으로 '{btype}' 소상공인을 위한 릴스 촬영 가이드 보고서를 작성해주세요.

반드시 아래 구조로 작성하세요:

### 📊 이번 주 분석 결과 요약
(전체 분석 결과를 2~3문장으로 요약)

### 🏆 터지는 릴스의 공통 공식
(상위 릴스의 공통점을 항목별로 정리. 각 항목에 이유도 1줄 추가)

### ⚡ 상위 vs 하위 핵심 차이
(가장 중요한 차이점 2~3가지. 구체적 수치 포함)

### 🎬 내일 당장 적용할 수 있는 촬영 팁
(실천 가능한 팁 4~5가지. 각 팁은 1줄로)

### 💡 이번 주 핵심 한 줄
(핵심을 한 문장으로 요약)
"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return message.content[0].text


# ── 스트리밍 버전 (Streamlit 실시간 출력용) ──

def generate_report_stream(report_input: dict):
    """
    보고서를 스트리밍으로 생성합니다. Streamlit st.write_stream()에 사용하세요.

    Usage:
        st.write_stream(generate_report_stream(report_input))
    """
    btype = report_input.get("business_type", "소상공인")
    total = report_input.get("total_analyzed", 0)
    top_count = report_input.get("top_count", 0)
    top_common = report_input.get("top_common", {})
    differences = report_input.get("key_differences", [])
    summaries = report_input.get("individual_summaries", [])

    user_prompt = f"""
다음은 인스타그램 릴스 분석 결과입니다. 업종은 '{btype}'입니다.

## 분석 개요
- 총 분석 영상 수: {total}개
- 상위(S/A급) 릴스: {top_count}개

## 상위 릴스 공통 패턴
{json.dumps(top_common, ensure_ascii=False, indent=2)}

## 상위 vs 하위 핵심 차이점
{chr(10).join(f"- {d}" for d in differences)}

## 상위 릴스 개별 요약
{chr(10).join(f"- [{s['tier']}] {s['reel_id']}: {s['summary']}" for s in summaries[:5])}

---
위 데이터를 바탕으로 '{btype}' 소상공인을 위한 릴스 촬영 가이드 보고서를 작성해주세요.

반드시 아래 구조로 작성하세요:

### 📊 이번 주 분석 결과 요약
### 🏆 터지는 릴스의 공통 공식
### ⚡ 상위 vs 하위 핵심 차이
### 🎬 내일 당장 적용할 수 있는 촬영 팁
### 💡 이번 주 핵심 한 줄
"""

    with client.messages.stream(
        model=MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text


# ── 빠른 테스트 ───────────────────────────────
if __name__ == "__main__":
    # 목업 데이터로 테스트
    mock_input = {
        "business_type": "카페",
        "total_analyzed": 15,
        "top_count": 6,
        "low_count": 9,
        "top_common": {
            "camera_angle": "탑뷰",
            "cut_speed": "빠름",
            "color_tone": "따뜻함",
            "bgm_mood": "신나는",
            "subtitle_position": "하단",
        },
        "key_differences": [
            "상위 릴스는 '탑뷰' 촬영 구도를 83% 사용하지만, 하위 릴스는 33%에 불과합니다.",
            "상위 릴스는 '빠름' 컷 편집 속도를 67% 사용하지만, 하위 릴스는 22%에 불과합니다.",
        ],
        "individual_summaries": [
            {"reel_id": "reel_001", "tier": "S", "score": 94.2,
             "summary": "탑뷰 구도와 빠른 컷 편집이 돋보이며, 첫 3초에 음료 클로즈업으로 시선을 잡음"},
        ],
    }

    print("=== 보고서 생성 중 ===")
    report = generate_report(mock_input)
    print(report)
