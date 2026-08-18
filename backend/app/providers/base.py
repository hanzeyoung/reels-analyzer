"""외부 의존 3종의 인터페이스. real/fake는 이 계약만 지키면 된다."""

from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.analyze import ReelAnalysis, VisionAnalysis
from app.schemas.collect import Account, RawReel
from app.schemas.common import Confidence
from app.schemas.compare import ComparisonResult
from app.schemas.guide import Guide
from app.schemas.requests import UserConstraints


class CollectProvider(ABC):
    @abstractmethod
    async def collect_reels(self, keyword: str, business_type: str) -> list[RawReel]:
        """키워드로 릴스 원본을 수집한다. 계정 정보는 다루지 않는다(별도 메서드)."""

    @abstractmethod
    async def fetch_accounts(self, usernames: list[str]) -> list[Account]:
        """계정 프로필(팔로워 수 등)을 조회한다.

        30일 캐시 판정(어떤 username을 조회할지 거를지)은 호출부(pipeline/collect.py)의
        책임이다 — provider는 DB를 모른다.
        """


class VisionProvider(ABC):
    @abstractmethod
    async def analyze_shots(self, frame_paths: list[Path], caption: str) -> VisionAnalysis:
        """컷별 대표 프레임을 보고 샷을 서술한다. 시각(초) 정보는 다루지 않는다."""


class WriterProvider(ABC):
    @abstractmethod
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
    ) -> Guide:
        """대조 결과 + 트랙별 릴스 분석으로 최종 가이드를 작성한다.

        원래 문서 주석은 `pool: ReelPool`을 받는 것으로 돼 있었으나, `ReelPool`의
        collected_count/after_recency_count 등 집계 필드는 P1에서 어디에도 저장되지
        않는 값이라(SESSION_LOG.md T-1.2 참조) 여기서 채우려면 지어내야 했다. 프롬프트가
        실제로 쓰는 건 breakout/big_account 릴스의 분석 결과뿐이라(ReelPool 전체가
        아니라) 인터페이스를 그만큼만 받게 좁혔다 — 판단(2026-08-14).

        confidence는 코드(comparing 단계 이후)가 ComparisonResult.sufficient/findings
        개수로 계산해서 넘긴다. 모델이 스스로 판단하지 않는다
        (docs/03-pipeline.md generating 참조).
        """
