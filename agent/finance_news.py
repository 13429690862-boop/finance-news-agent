"""Recent financial news collection and rule-based sentiment classification."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from importlib.util import find_spec
from typing import Any
from urllib.parse import quote_plus

from agent.finance_models import FinanceNewsItem, Holding


POSITIVE_KEYWORDS = [
    "利好", "上涨", "增长", "增持", "回购", "中标", "盈利", "超预期", "上调", "扩产", "突破",
    "创新高", "政策支持", "批准", "复苏", "分红", "positive", "beat", "growth", "upgrade",
    "buyback", "profit", "approval", "record high",
]
NEGATIVE_KEYWORDS = [
    "利空", "下跌", "亏损", "减持", "处罚", "调查", "诉讼", "暴雷", "违约", "降级", "裁员",
    "低于预期", "监管", "召回", "风险", "negative", "miss", "loss", "downgrade", "probe",
    "lawsuit", "default", "recall", "slump", "warning",
]
HIGH_IMPACT_KEYWORDS = [
    "财报", "业绩", "监管", "政策", "利率", "并购", "重组", "分红", "回购", "处罚", "调查",
    "earnings", "guidance", "rate", "merger", "acquisition", "regulator", "lawsuit",
]


def collect_finance_news(holdings: list[Holding], config: dict[str, Any]) -> tuple[list[FinanceNewsItem], dict[str, Any]]:
    """Collect recent news for holdings and broad market queries."""
    lookback_days = int(config.get("lookback_days", 7))
    max_per_holding = int(config.get("max_news_per_holding", 12))
    max_market_news = int(config.get("max_market_news", 20))
    items: list[FinanceNewsItem] = []
    source_status: dict[str, Any] = {}

    for holding in holdings:
        query = _holding_query(holding)
        rows, status = _collect_query(query, config, max_per_holding, lookback_days)
        _merge_status(source_status, status)
        for row in rows:
            row.holding_symbol = holding.symbol
            row.holding_name = holding.name
            row.query = query
        items.extend(rows)

    for query in config.get("market_queries", []) or []:
        rows, status = _collect_query(str(query), config, max_market_news, lookback_days)
        _merge_status(source_status, status)
        for row in rows:
            row.query = str(query)
        items.extend(rows)

    deduped = _dedupe_news(items)
    for item in deduped:
        classify_news_item(item)
    return deduped, {"sources": source_status, "total_after_dedupe": len(deduped)}


def _holding_query(holding: Holding) -> str:
    parts = [holding.name, holding.symbol, "股票 基金 财报 利好 利空" if holding.asset_type != "fund" else "基金 净值 持仓 利好 利空"]
    return " ".join(part for part in parts if part).strip()


def _collect_query(query: str, config: dict[str, Any], max_items: int, lookback_days: int) -> tuple[list[FinanceNewsItem], dict[str, Any]]:
    rows: list[FinanceNewsItem] = []
    status: dict[str, Any] = {}
    sources = config.get("sources", {}) if isinstance(config.get("sources"), dict) else {}
    google_cfg = sources.get("google_news_rss", {}) if isinstance(sources.get("google_news_rss"), dict) else {}
    gdelt_cfg = sources.get("gdelt", {}) if isinstance(sources.get("gdelt"), dict) else {}

    if google_cfg.get("enabled", True):
        rss_rows = _fetch_google_news_rss(
            query=query,
            max_items=max_items,
            language=str(config.get("language", "zh-CN")),
            country=str(config.get("country", "CN")),
            timeout_seconds=int(google_cfg.get("timeout_seconds", 15)),
        )
        rows.extend(rss_rows)
        status["google_news_rss"] = {"status": "ok", "count": status.get("google_news_rss", {}).get("count", 0) + len(rss_rows)}

    if gdelt_cfg.get("enabled", True):
        gdelt_rows = _fetch_gdelt_news(query=query, max_items=max_items, lookback_days=lookback_days, timeout_seconds=int(gdelt_cfg.get("timeout_seconds", 15)))
        rows.extend(gdelt_rows)
        status["gdelt"] = {"status": "ok", "count": status.get("gdelt", {}).get("count", 0) + len(gdelt_rows)}

    return rows[:max_items], status


def _fetch_google_news_rss(query: str, max_items: int, language: str, country: str, timeout_seconds: int) -> list[FinanceNewsItem]:
    if find_spec("httpx") is None:
        return []
    import httpx

    ceid = f"{country}:zh-Hans" if language.startswith("zh") else f"{country}:en"
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl={quote_plus(language)}&gl={quote_plus(country)}&ceid={quote_plus(ceid)}"
    try:
        with httpx.Client(timeout=timeout_seconds, headers={"User-Agent": "portfolio-news-agent/1.0"}) as client:
            response = client.get(url)
            response.raise_for_status()
            root = ET.fromstring(response.text)
    except Exception:
        return []

    rows: list[FinanceNewsItem] = []
    for node in root.findall(".//item")[:max_items]:
        title = _text(node.findtext("title"))
        link = _text(node.findtext("link"))
        published = _parse_rss_date(_text(node.findtext("pubDate")))
        source_node = node.find("source")
        source = _text(source_node.text if source_node is not None else "Google News")
        if title and link:
            rows.append(FinanceNewsItem(title=title, url=link, source=source or "Google News", published_at=published, summary=_text(node.findtext("description")), raw_metadata={"collector": "google_news_rss"}))
    return rows


def _fetch_gdelt_news(query: str, max_items: int, lookback_days: int, timeout_seconds: int) -> list[FinanceNewsItem]:
    if find_spec("httpx") is None:
        return []
    import httpx

    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc"
        f"?query={quote_plus(query)}&mode=ArtList&maxrecords={max(1, max_items)}"
        f"&format=json&sort=DateDesc&timespan={max(1, lookback_days)}d"
    )
    try:
        with httpx.Client(timeout=timeout_seconds, headers={"User-Agent": "portfolio-news-agent/1.0"}) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return []

    rows: list[FinanceNewsItem] = []
    for article in payload.get("articles", []) if isinstance(payload, dict) else []:
        if not isinstance(article, dict):
            continue
        title = _text(article.get("title"))
        link = _text(article.get("url"))
        if not title or not link:
            continue
        rows.append(
            FinanceNewsItem(
                title=title,
                url=link,
                source=_text(article.get("domain") or article.get("source") or "GDELT"),
                published_at=_text(article.get("seendate") or article.get("date") or datetime.now(UTC).isoformat()),
                summary=_text(article.get("snippet") or article.get("domain")),
                raw_metadata={"collector": "gdelt", "tone": article.get("tone"), "sourcecountry": article.get("sourcecountry")},
            )
        )
    return rows


def classify_news_item(item: FinanceNewsItem) -> FinanceNewsItem:
    text = f"{item.title} {item.summary}".lower()
    positive_hits = _keyword_hits(text, POSITIVE_KEYWORDS)
    negative_hits = _keyword_hits(text, NEGATIVE_KEYWORDS)
    impact_hits = _keyword_hits(text, HIGH_IMPACT_KEYWORDS)
    score = len(positive_hits) - len(negative_hits)
    item.sentiment_score = score
    if score > 0:
        item.sentiment = "positive"
    elif score < 0:
        item.sentiment = "negative"
    else:
        item.sentiment = "neutral"
    item.impact_score = min(5, max(1, 1 + len(impact_hits) + abs(score)))
    item.reasons = [f"positive:{kw}" for kw in positive_hits[:3]] + [f"negative:{kw}" for kw in negative_hits[:3]] + [f"impact:{kw}" for kw in impact_hits[:3]]
    return item


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    return [kw for kw in keywords if kw.lower() in text]


def _dedupe_news(items: list[FinanceNewsItem]) -> list[FinanceNewsItem]:
    seen: set[str] = set()
    out: list[FinanceNewsItem] = []
    for item in items:
        key = item.url.strip().lower() or re.sub(r"\s+", " ", item.title.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _merge_status(target: dict[str, Any], status: dict[str, Any]) -> None:
    for name, row in status.items():
        bucket = target.setdefault(name, {"status": row.get("status", "ok"), "count": 0})
        bucket["count"] = int(bucket.get("count", 0) or 0) + int(row.get("count", 0) or 0)
        bucket["status"] = row.get("status", bucket.get("status", "ok"))


def _parse_rss_date(value: str) -> str:
    if not value:
        return datetime.now(UTC).isoformat()
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat()
    except Exception:
        return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()
