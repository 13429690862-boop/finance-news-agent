"""Markdown/JSON reporting for the portfolio news monitor."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.finance_models import FinanceNewsItem, HoldingAssessment


def generate_finance_markdown_report(
    assessments: list[HoldingAssessment],
    market_news: list[FinanceNewsItem],
    summary: dict[str, Any],
    output_path: str | Path,
    source_status: dict[str, Any] | None = None,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# 持仓利好/利空消息与理财建议日报",
        "",
        f"生成时间：{datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}",
        "",
        "> 说明：本报告基于公开新闻标题/摘要和规则模型生成，仅用于投资研究辅助，不构成保证收益、个性化适当性结论或强制买卖指令。重大决策前请结合公告、财报、估值、流动性、仓位和个人风险承受能力复核。",
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
    if not assessments:
        lines.append("| 未配置持仓 | - | - | 0 | 0 | 0 | - | - | 请在 `configs/portfolio.yaml` 中添加持仓。 |")
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
