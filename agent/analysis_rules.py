from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ANALYST_PERSONA = (
    "你是一位经验丰富的理财顾问/基金分析师。"
    "你的分析必须用通俗语言解释专业概念，避免堆砌术语。"
    "你不能承诺收益，不能给出保证性结论，不能输出'必涨''稳赚''满仓'等表达。"
)


ANTI_HALLUCINATION_RULES = [
    "数字必须来自程序采集、行情数据或明确来源；没有来源的数字必须标注 [UNSOURCED]。",
    "政策、公告、监管文件必须带文号、发布日期或来源链接；缺失则标注 [UNSOURCED]。",
    "趋势判断必须量化，例如涨跌幅、均线位置、波动率、支撑位、压力位，不能只写'走势不错'。",
    "如果新闻为空、行情缺失或数据冲突，必须说明'数据不足'，不能编造原因。",
    "建议只能是研究辅助和风险提示，不能作为直接买卖指令。",
]


@dataclass
class VerificationResult:
    source_confidence: str
    data_gaps: list[str]
    source_register: list[str]
    search_keywords: list[str]
    warnings: list[str]


def _safe(value: Any, fallback: str = "[UNSOURCED]") -> str:
    if value is None:
        return fallback
    if isinstance(value, str) and not value.strip():
        return fallback
    return str(value)


def build_verification_result(
    *,
    holding_name: str,
    holding_symbol: str,
    news_count: int,
    positive_count: int,
    negative_count: int,
    technical_signal: Any | None = None,
    sources: dict[str, Any] | None = None,
) -> VerificationResult:
    data_gaps: list[str] = []
    source_register: list[str] = []
    warnings: list[str] = []

    if news_count == 0:
        data_gaps.append("近期待筛选新闻不足，消息面结论可靠性较低。")

    if technical_signal is None:
        data_gaps.append("缺少行情技术指标，无法量化趋势。")
    else:
        if getattr(technical_signal, "last_close", None) is None:
            data_gaps.append("缺少最新收盘价。")
        if getattr(technical_signal, "change_20d", None) is None:
            data_gaps.append("缺少近20日涨跌幅。")
        if getattr(technical_signal, "ma20", None) is None:
            data_gaps.append("缺少20日均线。")

    if sources:
        for source_name, source_info in sources.items():
            source_register.append(f"{source_name}: {_safe(source_info)}")
    else:
        source_register.append("[UNSOURCED] 未登记数据源状态。")

    if news_count == 0 and technical_signal is None:
        source_confidence = "low"
        warnings.append("新闻面和技术面数据均不足，本标的建议仅能作为低置信度观察意见。")
    elif data_gaps:
        source_confidence = "medium"
    else:
        source_confidence = "high"

    search_keywords = [
        f"{holding_name} {holding_symbol} 最新消息",
        f"{holding_name} {holding_symbol} 公告",
        f"{holding_name} {holding_symbol} 业绩",
        f"{holding_name} {holding_symbol} 走势",
        f"{holding_name} {holding_symbol} 风险",
    ]

    if positive_count == 0 and negative_count == 0:
        warnings.append("未形成明确利好/利空信号，不应仅凭消息面做交易决策。")

    return VerificationResult(
        source_confidence=source_confidence,
        data_gaps=data_gaps,
        source_register=source_register,
        search_keywords=search_keywords,
        warnings=warnings,
    )


def explain_risk_level(risk_level: str) -> str:
    if risk_level == "high":
        return "高风险：波动或不确定性较大，适合降低仓位敏感度，避免追涨。"
    if risk_level == "medium":
        return "中等风险：存在一定波动，需要结合仓位和趋势观察。"
    if risk_level == "low":
        return "低风险：当前数据没有显示明显异常，但仍需跟踪后续变化。"
    return "风险未知：数据不足，暂不能可靠判断。"


def explain_trend(trend: str) -> str:
    mapping = {
        "strong_uptrend": "强势上行：价格在多条均线上方，短中期趋势较强。",
        "uptrend": "上行趋势：价格表现相对健康，但仍需防范回撤。",
        "neutral": "震荡状态：趋势不明确，适合等待方向选择。",
        "downtrend": "下行趋势：短线偏弱，不适合激进加仓。",
        "weak": "弱势状态：中期趋势偏弱，应优先控制风险。",
        "unknown": "趋势未知：行情数据不足，不能判断趋势。",
    }
    return mapping.get(trend, f"{trend}：[UNSOURCED] 未识别趋势标签。")
