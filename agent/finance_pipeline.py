"""End-to-end portfolio news monitoring pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.finance_advisor import build_holding_assessments, build_portfolio_summary
from agent.finance_config import load_finance_config, load_portfolio
from agent.finance_news import collect_finance_news
from agent.finance_report import generate_finance_json_summary, generate_finance_markdown_report


def run_finance_daily_pipeline(
    portfolio_path: str | Path = "configs/portfolio.yaml",
    finance_config_path: str | Path = "configs/finance.yaml",
    markdown_report_path: str | Path | None = None,
    json_summary_path: str | Path | None = None,
) -> dict[str, Any]:
    config = load_finance_config(finance_config_path)
    holdings = load_portfolio(portfolio_path)
    news_items, collection_summary = collect_finance_news(holdings, config)
    market_news = [item for item in news_items if not item.holding_symbol]
    assessments = build_holding_assessments(holdings, news_items, config)
    summary = build_portfolio_summary(assessments, market_news)
    date_label = datetime.now(UTC).date().isoformat()
    report_path = Path(markdown_report_path or f"reports/{date_label}-finance-report.md")
    json_path = Path(json_summary_path) if json_summary_path is not None else None
    generate_finance_markdown_report(assessments, market_news, summary, report_path, collection_summary.get("sources", {}))
    if json_path is not None:
        generate_finance_json_summary(assessments, market_news, summary, json_path, collection_summary.get("sources", {}))
    return {
        "holding_count": len(holdings),
        "news_count": len(news_items),
        "market_news_count": len(market_news),
        "assessment_count": len(assessments),
        "summary": summary,
        "source_statuses": collection_summary.get("sources", {}),
        "report_path": str(report_path),
        "json_summary_path": str(json_path) if json_path is not None else None,
    }
