"""
릴스 수집부터 상위 릴스 분석 보고서 생성까지 한 번에 실행하는 스크립트.

옵션 없이 실행하면 터미널에서 키워드와 업종을 직접 입력합니다.
"""

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / ".python-packages"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "files"))

os.environ.setdefault("PYTHONUTF8", "1")

from app.api.reels_collector import download_top_reel_videos, get_top_reels
from gemini import analyze_top_reels


def ask_required(prompt: str) -> str:
    value = input(prompt).strip()
    if not value:
        raise ValueError("키워드는 반드시 입력해야 합니다.")
    return value


def ask_optional(prompt: str, default: str) -> str:
    value = input(prompt).strip()
    return value or default


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("0보다 큰 숫자를 입력하세요.")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="릴스 수집, 다운로드, Gemini 보고서 생성을 한 번에 실행합니다.")
    parser.add_argument("--keyword", default="", help="검색 키워드. 없으면 실행 중 입력합니다.")
    parser.add_argument("--business-type", default="", help="업종. 없으면 실행 중 입력합니다. 기본값: 카페")
    parser.add_argument("--top-n", type=positive_int, default=5, help="최종 확보할 영상 수")
    parser.add_argument("--candidate-multiplier", type=positive_int, default=3, help="다운로드 실패/제외 대비 후보 배수")
    parser.add_argument("--max-items", type=positive_int, default=20, help="Apify 1회 호출당 가져올 후보 수")
    parser.add_argument("--save-dir", default="videos", help="영상과 다운로드 로그 저장 폴더")
    parser.add_argument("--skip-report", action="store_true", help="영상 다운로드까지만 실행하고 Gemini 보고서는 생략합니다.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("=== 릴스 분석 보고서 생성기 ===")
    keyword = args.keyword.strip() or ask_required("검색 키워드를 입력하세요 (예: 성수동카페): ")
    business_type = args.business_type.strip() or ask_optional("업종을 입력하세요 (Enter: 카페): ", "카페")
    candidate_count = args.top_n * args.candidate_multiplier

    print("\n=== 1. 릴스 수집 및 스코어링 ===")
    top_reels = get_top_reels(
        keyword=keyword,
        max_items=args.max_items,
        top_n=candidate_count,
        save_dir=args.save_dir,
    )

    if not top_reels:
        raise RuntimeError("수집된 릴스가 없습니다.")

    print(f"\n=== 2. 상위 {args.top_n}개 영상 다운로드 ===")
    downloaded_reels = download_top_reel_videos(
        top_reels,
        save_dir=args.save_dir,
        keyword=keyword,
        target_count=args.top_n,
    )
    print(f"다운로드 완료: {len(downloaded_reels)}개")
    if len(downloaded_reels) < args.top_n:
        raise RuntimeError(f"키워드 관련 영상 {args.top_n}개 확보 실패: {len(downloaded_reels)}개만 확보됨")

    if args.skip_report:
        print("\n=== 완료 ===")
        print("보고서 생성은 --skip-report 옵션으로 생략했습니다.")
        return

    print("\n=== 3. 초 단위 보고서 생성 ===")
    report_path = analyze_top_reels(
        limit=args.top_n,
        business_type=business_type,
        keyword=keyword,
    )

    print("\n=== 완료 ===")
    print(f"보고서 파일: {report_path}")


if __name__ == "__main__":
    main()