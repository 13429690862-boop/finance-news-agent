from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.finance_models import FinanceNewsItem, HoldingAssessment

try:
    from agent.analysis_rules import (
        ANALYST_PERSONA,
        ANTI_HALLUCINATION_RULES,
        build_verification_result,
        explain_risk_level,
        explain_trend,
    )
except Exception:
    ANALYST_PERSONA = (
        "你是一位经验丰富的理财顾问/基金分析师。"
        "你的分析必须用通俗语言解释专业概念，避免堆砌术语。"
        "你不能承诺收益，不能给出保证性结论。"
    )
    ANTI_HALLUCINATION_RULES = [
        "数字必须来自程序采集、行情数据或明确来源；没有来源的数字必须标注 [UNSOURCED]。",
        "政策、公告、监管文件必须带文号、发布日期或来源链接；缺失则标注 [UNSOURCED]。",
        "趋势判断必须量化，例如涨跌幅、均线位置、波动率、支撑位、压力位。",
        "如果新闻为空、行情缺失或数据冲突，必须说明数据不足，不能编造原因。",
        "建议只能作为研究辅助和风险提示，不能作为直接买卖指令。",
    ]

    def explain_risk_level(risk_level: str) -> str:
        mapping = {
            "high": "高风险：波动或不确定性较大，应优先控制回撤。",
            "medium": "中等风险：存在一定波动，需要结合仓位和趋势观察。",
            "low": "低风险：当前数据没有显示明显异常，但不代表没有风险。",
        }
        return mapping.get(risk_level, "风险未知：数据不足，暂不能可靠判断。")

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

    def build_verification_result(
        *,
        holding_name: str,
        holding_symbol: str,
        news_count: int,
        positive_count: int,
        negative_count: int,
        technical_signal: Any | None = None,
        sources: dict[str, Any] | None = None,
    ) -> Any:
        class Result:
            source_confidence = "medium"
            data_gaps = []
            source_register = []
            search_keywords = []
            warnings = []

        result = Result()
        if news_count == 0:
            result.data_gaps.append("近期待筛选新闻不足，消息面结论可靠性较低。")
        if technical_signal is None:
            result.data_gaps.append("缺少行情技术指标，无法量化趋势。")
        result.source_confidence = "low" if result.data_gaps else "high"
        result.source_register = [f"{k}: {v}" for k, v in (sources or {}).items()] or ["[UNSOURCED] 未登记数据源状态。"]
        result.search_keywords = [
            f"{holding_name} {holding_symbol} 最新消息",
            f"{holding_name} {holding_symbol} 公告",
            f"{holding_name} {holding_symbol} 业绩",
            f"{holding_name} {holding_symbol} 走势",
            f"{holding_name} {holding_symbol} 风险",
        ]
        if positive_count == 0 and negative_count == 0:
            result.warnings.append("未形成明确利好/利空信号，不应仅凭消息面做交易决策。")
        return result


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    return str(value).replace("|", "｜").replace("\n", " ").strip()


def _fmt_number(value: float | None) -> str:
    if value is None:
        return "无数据"
    try:
        return f"{float(value):.2f}"
    except Exception:
        return "无数据"


def _fmt_percent(value: float | None) -> str:
    if value is None:
        return "无数据"
    try:
        return f"{float(value):.2f}%"
    except Exception:
        return "无数据"


def _fmt_datetime(value: Any) -> str:
    if value is None:
        return "未知时间"
    try:
        return value.isoformat()
    except Exception:
        return str(value)


def _assessment_value(row: HoldingAssessment, name: str, fallback: Any = None) -> Any:
    return getattr(row, name, fallback)


def _news_value(item: FinanceNewsItem, name: str, fallback: Any = None) -> Any:
    return getattr(item, name, fallback)


def generate_finance_markdown_report(
    assessments: list[HoldingAssessment],
    market_news: list[FinanceNewsItem],
    summary: dict[str, Any],
    output_path: str | Path,
    source_status: dict[str, Any] | None = None,
    technical_signals: list[Any] | None = None,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "# 持仓利好/利空消息与理财建议日报",
        "",
        "## 分析师角色与反幻觉规则",
        "",
        f"- 角色设定：{ANALYST_PERSONA}",
        "- 重要说明：本报告用于投资研究辅助，不构成保证收益、个性化适当性结论或强制买卖指令。",
        "",
        "### 硬规则",
        "",
    ]

    for rule in ANTI_HALLUCINATION_RULES:
        lines.append(f"- {rule}")

    lines.extend(
        [
            "",
            "### 交叉验证流程",
            "",
            "- SA 数据矛盾：检查新闻、行情、持仓建议之间是否互相冲突。",
            "- SB 信息缺口：如果没有新闻、没有行情或缺少公告来源，必须标注数据不足。",
            "- SC 来源登记：报告记录数据源状态，不把无来源内容写成事实。",
            "- SD 检索关键词：为每个标的登记后续可人工复核的关键词。",
            "",
            f"- 生成时间：{datetime.now(UTC).replace(microsecond=0).isoformat()}",
            "",
            "## 组合概览",
            "",
            f"- 持仓数量：{summary.get('holding_count', 0)}",
            f"- 高风险观察持仓：{summary.get('high_risk_holding_count', 0)}",
            f"- 中风险观察持仓：{summary.get('medium_risk_holding_count', 0)}",
            f"- 市场消息面：{summary.get('market_tone', '中性')}",
            f"- 市场利好/利空/中性消息：{summary.get('market_positive_news_count', 0)} / {summary.get('market_negative_news_count', 0)} / {summary.get('market_neutral_news_count', 0)}",
            "",
            "## 持仓建议摘要",
            "",
            "| 标的 | 类型 | 市场 | 利好 | 利空 | 净分 | 风险 | 建议动作 | 建议 |",
            "| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |",
        ]
    )

    if not assessments:
        lines.append("| 暂无持仓建议 | - | - | 0 | 0 | 0 | - | - | 请在 configs/portfolio.yaml 中添加持仓。 |")
    else:
        for row in assessments:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"{_cell(_assessment_value(row, 'name'))}（{_cell(_assessment_value(row, 'symbol'))}）",
                        _cell(_assessment_value(row, "asset_type")),
                        _cell(_assessment_value(row, "market")),
                        str(_assessment_value(row, "positive_count", _assessment_value(row, "positive_news_count", 0))),
                        str(_assessment_value(row, "negative_count", _assessment_value(row, "negative_news_count", 0))),
                        str(_assessment_value(row, "net_sentiment_score", _assessment_value(row, "net_score", 0))),
                        _cell(_assessment_value(row, "risk_level")),
                        _cell(_assessment_value(row, "action")),
                        _cell(_assessment_value(row, "advice")),
                    ]
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "## 市场消息",
            "",
        ]
    )

    if not market_news:
        lines.append("近期待筛选市场新闻不足，市场层面判断置信度较低。")
    else:
        for item in market_news[:10]:
            title = _cell(_news_value(item, "title"))
            source = _cell(_news_value(item, "source"))
            published = _fmt_datetime(_news_value(item, "published_at"))
            url = _cell(_news_value(item, "url"))
            lines.append(f"- [{published}] {title}｜来源：{source}｜链接：{url}")

    lines.extend(
        [
            "",
            "## 个股 / 基金走势技术分析",
            "",
        ]
    )

    if not technical_signals:
        lines.append("未获取到有效行情数据，暂不生成技术面分析。")
    else:
        for signal in technical_signals:
            lines.extend(
                [
                    f"### {signal.name}（{signal.symbol}）",
                    "",
                    f"- 数据代码：{signal.yahoo_symbol}",
                    f"- 最新收盘价：{_fmt_number(signal.last_close)}",
                    f"- 近 5 日涨跌幅：{_fmt_percent(signal.change_5d)}",
                    f"- 近 20 日涨跌幅：{_fmt_percent(signal.change_20d)}",
                    f"- MA5 / MA20 / MA60：{_fmt_number(signal.ma5)} / {_fmt_number(signal.ma20)} / {_fmt_number(signal.ma60)}",
                    f"- 近 20 日波动率：{_fmt_percent(signal.volatility_20d)}",
                    f"- 趋势判断：{signal.trend}。通俗解释：{explain_trend(signal.trend)}",
                    f"- 技术风险：{signal.risk_level}。通俗解释：{explain_risk_level(signal.risk_level)}",
                    f"- 参考支撑位：{_fmt_number(signal.support)}",
                    f"- 参考压力位：{_fmt_number(signal.resistance)}",
                    f"- 分析师视角：{signal.analyst_view}",
                    "",
                ]
            )

    lines.extend(
        [
            "",
            "## 交叉验证与信息缺口登记",
            "",
            "本节用于防止模型幻觉：凡是缺少来源、缺少行情或消息不足的地方，均明确标注。",
            "",
        ]
    )

    technical_by_symbol = {}
    if technical_signals:
        technical_by_symbol = {str(signal.symbol): signal for signal in technical_signals}

    for row in assessments:
        name = _cell(_assessment_value(row, "name"))
        symbol = _cell(_assessment_value(row, "symbol"))
        positive_count = int(_assessment_value(row, "positive_count", _assessment_value(row, "positive_news_count", 0)) or 0)
        negative_count = int(_assessment_value(row, "negative_count", _assessment_value(row, "negative_news_count", 0)) or 0)
        signal = technical_by_symbol.get(str(symbol))

        verification = build_verification_result(
            holding_name=name,
            holding_symbol=symbol,
            news_count=positive_count + negative_count,
            positive_count=positive_count,
            negative_count=negative_count,
            technical_signal=signal,
            sources=source_status,
        )

        lines.extend(
            [
                f"### {name}（{symbol}）",
                "",
                f"- 来源置信度：{verification.source_confidence}",
                f"- SA 数据矛盾检查：{'未发现明显冲突' if not verification.warnings else '；'.join(verification.warnings)}",
                f"- SB 信息缺口：{'无明显缺口' if not verification.data_gaps else '；'.join(verification.data_gaps)}",
                "- SC 来源登记：",
            ]
        )

        for source in verification.source_register:
            lines.append(f"  - {source}")

        lines.append("- SD 后续检索关键词：")
        for keyword in verification.search_keywords:
            lines.append(f"  - {keyword}")

        lines.append("")

    lines.extend(
        [
            "",
            "## 数据源状态",
            "",
        ]
    )

    if not source_status:
        lines.append("- [UNSOURCED] 未登记数据源状态。")
    else:
        for name, status in source_status.items():
            lines.append(f"- {name}: {_cell(status)}")

    lines.extend(
        [
            "",
            "## 风险提示",
            "",
            "- 本报告只用于辅助研究，不构成投资建议或收益承诺。",
            "- 若新闻、行情、公告、财报之间存在矛盾，应优先以正式公告、交易所披露和基金公司披露为准。",
            "- 找不到可靠数据时，本报告应标注 [UNSOURCED] 或数据不足，不应捏造结论。",
        ]
    )

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def generate_finance_json_summary(
    assessments: list[HoldingAssessment],
    market_news: list[FinanceNewsItem],
    summary: dict[str, Any],
    output_path: str | Path,
    source_status: dict[str, Any] | None = None,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "summary": summary,
        "source_status": source_status or {},
        "assessments": [
            {
                "name": _assessment_value(row, "name"),
                "symbol": _assessment_value(row, "symbol"),
                "asset_type": _assessment_value(row, "asset_type"),
                "market": _assessment_value(row, "market"),
                "positive_count": _assessment_value(row, "positive_count", _assessment_value(row, "positive_news_count", 0)),
                "negative_count": _assessment_value(row, "negative_count", _assessment_value(row, "negative_news_count", 0)),
                "net_sentiment_score": _assessment_value(row, "net_sentiment_score", _assessment_value(row, "net_score", 0)),
                "risk_level": _assessment_value(row, "risk_level"),
                "action": _assessment_value(row, "action"),
                "advice": _assessment_value(row, "advice"),
            }
            for row in assessments
        ],
        "market_news": [
            {
                "title": _news_value(item, "title"),
                "url": _news_value(item, "url"),
                "source": _news_value(item, "source"),
                "published_at": _fmt_datetime(_news_value(item, "published_at")),
                "summary": _news_value(item, "summary"),
            }
            for item in market_news
        ],
    }

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
