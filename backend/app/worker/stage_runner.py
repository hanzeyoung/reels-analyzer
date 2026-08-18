"""`make stage S=<name> F=<fixture>` 진입점. 단일 단계만 fixture로 독립 실행한다."""

import argparse
import asyncio

from app.pipeline import analyze, collect, compare, frames, guide, score

STAGES = {
    "collect": collect,
    "score": score,
    "frames": frames,
    "analyze": analyze,
    "compare": compare,
    "guide": guide,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="단일 파이프라인 단계 실행")
    parser.add_argument("--stage", "-S", required=True, choices=sorted(STAGES))
    parser.add_argument("--fixture", "-F", required=True)
    args = parser.parse_args()

    module = STAGES[args.stage]
    print(f"[stage={args.stage}] fixture={args.fixture}")
    asyncio.run(module.run(args.fixture))
    print("완료 (P0 스켈레톤: 실제 로직 없음)")


if __name__ == "__main__":
    main()
