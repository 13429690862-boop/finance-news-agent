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
    holding_name = getattr(holding, "name", "该标的")
    symbol = getattr(holding, "symbol", "")
    asset_type = getattr(holding, "asset_type", "")
    market = getattr(holding, "market", "")
    target_weight = getattr(holding, "target_weight", None)

    if target_weight is None:
        weight_text = "目标仓位未填写，因此仓位建议只能作为定性参考。[UNSOURCED]"
    else:
        weight_text = f"当前配置目标仓位为 {target_weight:.0%}，后续建议应围绕这个比例做再平衡，而不是根据单条新闻频繁交易。"

    asset_note = "基金/ETF更适合结合趋势、估值和组合配置做再平衡，不建议过度短线交易。"
    if asset_type == "stock":
        asset_note = "个股波动通常高于宽基基金，建议设置单票仓位上限，并避免因单日新闻大幅追涨杀跌。"
    elif asset_type == "fund":
        asset_note = "基金/ETF更适合结合趋势、估值、跟踪指数和组合配置做再平衡，不建议过度短线交易。"

    risk_note = {
        "high": "风险等级偏高，说明该标的当前可能存在较高波动或负面信号，优先级应放在控制回撤，而不是追求短线收益。",
        "medium": "风险等级中等，说明可以继续持有观察，但需要设置明确的复核条件。",
        "low": "风险等级较低，说明当前数据没有显示明显异常，但这不代表没有风险。",
    }.get(risk_level, "风险等级数据不足，不能形成高置信度判断。[UNSOURCED]")

    if action == "trim_risk":
        return (
            f"结论：{holding_name}（{symbol}）建议优先降低风险暴露。"
            f"原因：当前风险信号偏高，继续维持过高仓位可能放大组合波动。"
            f"{weight_text}"
            f"风险解释：{risk_note}"
            f"操作纪律：如果后续继续出现利空消息、跌破关键均线、放量下跌或正式公告转弱，可考虑分批降低仓位；不建议情绪化一次性清仓。"
            f"通俗理解：这不是判断它一定会跌，而是先把可能的亏损幅度控制住。"
        )

    if action == "watch":
        return (
            f"结论：{holding_name}（{symbol}）进入重点观察状态。"
            f"原因：当前消息面或风险信号还不足以直接支持大幅调整，但已经需要提高跟踪频率。"
            f"{weight_text}"
            f"风险解释：{risk_note}"
            f"观察条件：重点看三件事：第一，是否跌破20日均线或前期支撑位；第二，是否出现正式公告、财报或政策层面的负面变化；第三，同类资产是否同步走弱。"
            f"操作纪律：暂不建议追涨加仓，适合等待更明确的数据、公告或趋势信号。"
        )

    if action == "review_add":
        return (
            f"结论：{holding_name}（{symbol}）可以评估是否分批加仓，但不建议一次性追高。"
            f"原因：当前利好信号相对较多，但利好新闻不等于价格一定上涨，还需要结合估值、趋势、成交量和组合仓位判断。"
            f"{weight_text}"
            f"风险解释：{risk_note}"
            f"执行方式：如果确实要加仓，更适合分批执行，例如等待回踩支撑位、放量突破压力位或基本面数据确认后再行动。"
            f"通俗理解：好消息只是加分项，不是直接买入理由。"
        )

    if action == "rebalance":
        return (
            f"结论：{holding_name}（{symbol}）建议从组合角度做再平衡。"
            f"原因：当前问题不一定来自单个标的本身，而可能来自仓位集中、行业相关性过高或同类资产重复配置。"
            f"{weight_text}"
            f"风险解释：{risk_note}"
            f"操作纪律：优先检查该标的及同赛道资产合计占比。如果同类资产占比过高，可以逐步分散到低相关资产或现金类资产。"
            f"通俗理解：再平衡不是看空，而是避免组合被单一方向拖累。"
        )

    return (
        f"结论：{holding_name}（{symbol}）暂以持有观察为主。"
        f"原因：当前可验证消息不足，不能仅凭新闻面做加减仓判断。"
        f"{weight_text}"
        f"风险解释：{risk_note}"
        f"资产特征：{asset_note}"
        f"复核条件：后续重点看三项：第一，仓位是否超过原计划；第二，价格是否跌破关键均线或支撑位；第三，是否有正式公告、业绩变化或政策变化。"
        f"反幻觉说明：如果缺少可靠新闻、公告或行情数据，本报告不会编造原因，而应标注数据不足或 [UNSOURCED]。"
    )
