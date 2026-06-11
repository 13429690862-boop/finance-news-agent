"""Rule-based portfolio assessment built from recent positive/negative news."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from agent.finance_models import FinanceNewsItem, Holding, HoldingAssessment


def build_holding_assessments(
    holdings: list[Holding],
    news_items: list[FinanceNewsItem],
    config: dict[str, Any],
) -> list[HoldingAssessment]:
    """Create non-guaranteed, rule-based advisory notes for each holding."""
    by_symbol: dict[str, list[FinanceNewsItem]] = defaultdict(list)
    for item in news_items:
        if item.holding_symbol:
            by_symbol[item.holding_symbol].append(item)

    assessments: list[HoldingAssessment] = []
    risk_cfg = config.get("risk", {}) if isinstance(config.get("risk"), dict) else {}
    high_negative_count = int(risk_cfg.get("high_negative_count", 3))
    high_negative_score = int(risk_cfg.get("high_negative_score", -5))
    positive_review_score = int(risk_cfg.get("positive_review_score", 4))
    max_single_asset_target_weight = float(risk_cfg.get("max_single_asset_target_weight", 0.25))

    for holding in holdings:
        rows = sorted(by_symbol.get(holding.symbol, []), key=lambda item: (item.impact_score, abs(item.sentiment_score)), reverse=True)
        positive = [item for item in rows if item.sentiment == "positive"]
        negative = [item for item in rows if item.sentiment == "negative"]
        neutral = [item for item in rows if item.sentiment == "neutral"]
        net_score = sum(item.sentiment_score * item.impact_score for item in rows)

        risk_level = "low"
        action = "hold"
        rationale: list[str] = []

        if len(negative) >= high_negative_count or net_score <= high_negative_score:
            risk_level = "high"
            action = "trim_risk"
            rationale.append("近期负面消息数量或加权负面分数偏高，优先控制单一持仓风险。")
        elif negative and net_score < 0:
            risk_level = "medium"
            action = "watch"
            rationale.append("存在负面消息，尚未达到高风险阈值，建议列入观察清单。")
        elif net_score >= positive_review_score and positive:
            risk_level = "low"
            action = "review_add"
            rationale.append("近期正面消息占优，可结合估值、仓位和基本面复核是否继续持有或小幅优化。")
        else:
            rationale.append("近期消息面没有形成明确方向，维持纪律化观察。")

        if holding.target_weight is not None and holding.target_weight > max_single_asset_target_weight:
            risk_level = "high" if risk_level == "medium" else risk_level
            action = "rebalance" if action == "hold" else action
            rationale.append(f"目标权重 {holding.target_weight:.0%} 高于单一资产参考上限 {max_single_asset_target_weight:.0%}。")

        advice = _advice_text(action, holding, risk_level)
        assessments.append(
            HoldingAssessment(
                symbol=holding.symbol,
                name=holding.name,
                asset_type=holding.asset_type,
                market=holding.market,
                positive_count=len(positive),
                negative_count=len(negative),
                neutral_count=len(neutral),
                net_sentiment_score=net_score,
                risk_level=risk_level,  # type: ignore[arg-type]
                action=action,  # type: ignore[arg-type]
                advice=advice,
                rationale=rationale,
                top_positive_news=positive[:3],
                top_negative_news=negative[:3],
                top_neutral_news=neutral[:3],
            )
        )

    assessments.sort(key=lambda row: ({"high": 0, "medium": 1, "low": 2}[row.risk_level], -abs(row.net_sentiment_score), row.symbol))
    return assessments


def build_portfolio_summary(assessments: list[HoldingAssessment], market_news: list[FinanceNewsItem]) -> dict[str, Any]:
    positives = sum(item.sentiment == "positive" for item in market_news)
    negatives = sum(item.sentiment == "negative" for item in market_news)
    neutral = sum(item.sentiment == "neutral" for item in market_news)
    high_risk = sum(row.risk_level == "high" for row in assessments)
    medium_risk = sum(row.risk_level == "medium" for row in assessments)
    tone = "中性"
    if negatives > positives:
        tone = "偏谨慎"
    elif positives > negatives:
        tone = "偏积极"
    return {
        "holding_count": len(assessments),
        "high_risk_holding_count": high_risk,
        "medium_risk_holding_count": medium_risk,
        "market_positive_news_count": positives,
        "market_negative_news_count": negatives,
        "market_neutral_news_count": neutral,
        "market_tone": tone,
    }


def _advice_text(action: str, holding: Holding, risk_level: str) -> str:
    if action == "trim_risk":
        return "偏防守：不要追高加仓；优先复核仓位、止损/止盈纪律和基本面变化，必要时分批降低风险敞口。"
    if action == "watch":
        return "观察为主：保持原计划，但将负面事件、公告和后续财报列为跟踪重点。"
    if action == "review_add":
        return "审慎积极：消息面偏正面，但仍需结合估值、现金流、行业景气度和自身仓位，再决定是否继续持有或小幅优化。"
    if action == "rebalance":
        return "再平衡：仓位集中度偏高时，优先考虑分散到低相关资产或现金类资产。"
    return "维持纪律：消息面不足以支持重大调整，按既定资产配置和风险承受能力执行。"
