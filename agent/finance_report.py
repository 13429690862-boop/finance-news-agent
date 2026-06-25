"""Markdown/JSON reporting for the portfolio news monitor."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.analysis_rules import (
    ANALYST_PERSONA,
    ANTI_HALLUCINATION_RULES,
    build_verification_result,
    explain_risk_level,
    explain_trend,
)

from agent.finance_models import FinanceNewsItem, HoldingAssessment
def _fmt_number(value: float | None) -> str:
    if value is None:
        return "无数据"
    return f"{value:.2f}"


def _fmt_percent(value: float | None) -> str:
    if value is None:
        return "无数据"
    return f"{value:.2f}%"

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
        ]
    )

    if not assessments:
    for row in assessments:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(f"{row.name} ({row.symbol})"),
                    _cell(row.asset_type),
                    _cell(row.market),
                    str(row.positive_count),
                    str(row.negative_count),
                    str(row.net_sentiment_score),
                    _cell(row.risk_level),
                    _cell(row.action),
                    _cell(row.advice),
                ]
            )
            + " |"
        )

    lines.extend(["", "## 持仓明细", ""])
    for row in assessments:
        lines.extend(
            [
                f"### {row.name} ({row.symbol})",
                "",
                f"- 风险等级：{row.risk_level}",
                f"- 建议动作：{row.action}",
                f"- 建议：{row.advice}",
                f"- 判断依据：{'；'.join(row.rationale) if row.rationale else '无'}",
                "",
                "#### 主要利好",
            ]
        )
        _append_news_list(lines, row.top_positive_news)
        lines.append("#### 主要利空")
        _append_news_list(lines, row.top_negative_news)
        lines.append("#### 其他相关消息")
        _append_news_list(lines, row.top_neutral_news)
        lines.append("")

    lines.extend(["## 市场层面近期消息", ""])
    _append_news_list(lines, market_news[:10])

    lines.extend(["", "## 数据源状态", ""])
    for name, status in (source_status or {}).items():
        lines.append(f"- {name}: {status}")
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
        technical_by_symbol = {
            signal.symbol: signal for signal in technical_signals
        }

    for assessment in assessments:
        signal = technical_by_symbol.get(assessment.symbol)

        verification = build_verification_result(
            holding_name=assessment.name,
            holding_symbol=assessment.symbol,
            news_count=assessment.positive_news_count + assessment.negative_news_count,
            positive_count=assessment.positive_news_count,
            negative_count=assessment.negative_news_count,
            technical_signal=signal,
            sources=source_status,
        )

        lines.extend(
            [
                f"### {assessment.name}（{assessment.symbol}）",
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
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
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
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "disclaimer": "Rule-based research aid only; not guaranteed returns or individualized suitability advice.",
        "summary": summary,
        "source_status": source_status or {},
        "assessments": [row.model_dump() for row in assessments],
        "market_news": [item.model_dump() for item in market_news],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _append_news_list(lines: list[str], items: list[FinanceNewsItem]) -> None:
    if not items:
        lines.append("- 暂无。")
        lines.append("")
        return
    for item in items:
        reason = f"；原因：{', '.join(item.reasons)}" if item.reasons else ""
        lines.append(f"- [{_inline(item.title)}]({item.url}) — {item.source}，{item.published_at}，{item.sentiment}，影响分 {item.impact_score}{reason}")
    lines.append("")


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _inline(value: Any) -> str:
    return str(value).replace("[", "\\[").replace("]", "\\]").replace("\n", " ")
