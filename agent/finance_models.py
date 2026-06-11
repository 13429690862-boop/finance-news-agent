"""Data contracts for portfolio news monitoring and advisory reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Sentiment = Literal["positive", "negative", "neutral"]
RiskLevel = Literal["low", "medium", "high"]
Action = Literal["hold", "watch", "trim_risk", "review_add", "rebalance"]


@dataclass
class Holding:
    """A stock, ETF, mutual fund, or cash-like holding configured by the operator."""

    symbol: str
    name: str
    asset_type: str = "stock"
    market: str = "unknown"
    quantity: float | None = None
    cost_basis: float | None = None
    target_weight: float | None = None
    notes: str = ""

    def label(self) -> str:
        code = self.symbol.strip()
        display = self.name.strip() or code
        return f"{display} ({code})" if code else display

    def model_dump(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class FinanceNewsItem:
    """A normalized recent news item linked to one holding or the broader market."""

    title: str
    url: str
    source: str
    published_at: str
    summary: str = ""
    query: str = ""
    holding_symbol: str = ""
    holding_name: str = ""
    sentiment: Sentiment = "neutral"
    sentiment_score: int = 0
    impact_score: int = 1
    reasons: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class HoldingAssessment:
    """Rule-based assessment for a configured holding."""

    symbol: str
    name: str
    asset_type: str
    market: str
    positive_count: int
    negative_count: int
    neutral_count: int
    net_sentiment_score: int
    risk_level: RiskLevel
    action: Action
    advice: str
    rationale: list[str]
    top_positive_news: list[FinanceNewsItem] = field(default_factory=list)
    top_negative_news: list[FinanceNewsItem] = field(default_factory=list)
    top_neutral_news: list[FinanceNewsItem] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        payload = self.__dict__.copy()
        for key in ("top_positive_news", "top_negative_news", "top_neutral_news"):
            payload[key] = [item.model_dump() for item in payload[key]]
        return payload
