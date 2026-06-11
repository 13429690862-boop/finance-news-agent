"""Stack Exchange source collector."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import find_spec
from dataclasses import dataclass
from typing import Any

from agent.models import RawItem
from agent.sources.base import SourceCollector


class StackExchangeCollector(SourceCollector):
    """Collect demand-signal raw items from the Stack Exchange search API."""

    base_url = "https://api.stackexchange.com/2.3/search"
    source_type = "qa"

    def __init__(
        self,
        site: str = "stackoverflow",
        sites: list[str] | None = None,
        timeout_seconds: int = 15,
        user_agent: str = "china-demand-agent/phase-2c",
    ) -> None:
        configured_sites = sites if isinstance(sites, list) else [site]
        safe_sites = [str(value).strip() for value in configured_sites if str(value).strip()]
        self.sites = safe_sites or ["stackoverflow"]
        self.site = self.sites[0]
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    def collect(self, queries: list[str], max_items: int) -> list[RawItem]:
        if max_items <= 0 or not queries:
            return []

        results: list[RawItem] = []
        seen_keys: set[tuple[str, str]] = set()
        self.last_query_metrics: dict[str, Any] = {
            "strict_query_count": 0,
            "fallback_query_count": 0,
            "zero_result_query_count": 0,
            "site_collected_counts": {},
        }

        for query in queries:
            for site in self.sites:
                if len(results) >= max_items:
                    break
                query_plan = stackexchange_query_plan(query)
                self.last_query_metrics["strict_query_count"] += 1
                questions = self._fetch_items_for_query(query_plan.strict_phrase, max_items=max_items, site=site)
                adapted_query = query_plan.strict_phrase
                adaptation_stage = "strict"

                if not questions and query_plan.fallback_phrase:
                    self.last_query_metrics["fallback_query_count"] += 1
                    questions = self._fetch_items_for_query(query_plan.fallback_phrase, max_items=max_items, site=site)
                    adapted_query = query_plan.fallback_phrase
                    adaptation_stage = "fallback"

                if not questions:
                    self.last_query_metrics["zero_result_query_count"] += 1
                    continue

                for question in questions:
                    if len(results) >= max_items:
                        break
                    item = self._question_to_raw_item(question, query, site=site, adapted_query=adapted_query, adaptation_stage=adaptation_stage)
                    if item is None:
                        continue
                    dedupe_key = (item.url.strip().lower(), item.title.strip().lower())
                    if dedupe_key in seen_keys:
                        continue
                    seen_keys.add(dedupe_key)
                    results.append(item)
                    site_counts = self.last_query_metrics.setdefault("site_collected_counts", {})
                    site_counts[site] = site_counts.get(site, 0) + 1
            if len(results) >= max_items:
                break

        return results

    def _fetch_items_for_query(self, query: str, max_items: int, site: str) -> list[dict[str, Any]]:
        try:
            payload = self._fetch_questions(query, max_items=max_items, site=site)
        except Exception:
            payload = {}
        questions = payload.get("items", []) if isinstance(payload, dict) else []
        return questions if isinstance(questions, list) else []

    def _fetch_questions(self, query: str, max_items: int, site: str) -> dict[str, Any]:
        if find_spec("httpx") is None:
            return {}

        import httpx

        params = {
            "order": "desc",
            "sort": "relevance",
            "intitle": query,
            "site": site,
            "pagesize": max(1, min(max_items, 100)),
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds, headers={"User-Agent": self.user_agent}) as client:
                response = client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _question_to_raw_item(self, question: Any, query: str, site: str, adapted_query: str, adaptation_stage: str) -> RawItem | None:
        if not isinstance(question, dict):
            return None

        title = _clean_text(question.get("title"))
        url = _clean_text(question.get("link"))
        if not title or not url:
            return None

        tags = question.get("tags") if isinstance(question.get("tags"), list) else []
        tag_text = ", ".join(_clean_text(tag) for tag in tags if _clean_text(tag))
        context = _clean_text(question.get("content_license") or question.get("question_id"))
        content = " | ".join(part for part in [title, tag_text or context] if part)
        if not content:
            content = title

        creation_date = question.get("creation_date")
        published_at = ""
        if isinstance(creation_date, (int, float)):
            published_at = datetime.fromtimestamp(creation_date, tz=UTC).isoformat()

        owner = question.get("owner") if isinstance(question.get("owner"), dict) else {}
        author = _clean_text(owner.get("display_name"))

        metadata = {
            "score": question.get("score"),
            "answer_count": question.get("answer_count"),
            "tags": tags,
            "site": site,
            "question_id": question.get("question_id"),
            "adapted_query": adapted_query,
            "adaptation_stage": adaptation_stage,
            "owner": {
                key: owner.get(key)
                for key in ("display_name", "link", "user_id", "user_type")
                if key in owner
            },
        }

        return RawItem(
            source="stackexchange",
            source_type="qa",
            url=url,
            title=title,
            content=content,
            author=author,
            published_at=published_at,
            fetched_at=datetime.now(UTC).isoformat(),
            query=query,
            language="en",
            raw_metadata=metadata,
        )


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


@dataclass(frozen=True)
class StackExchangeQueryPlan:
    strict_phrase: str
    fallback_phrase: str


def stackexchange_query_plan(query: str) -> StackExchangeQueryPlan:
    text = _clean_text(query)
    lowered = text.lower()

    if "wechat pay" in lowered and ("shopify" in lowered or "checkout" in lowered):
        return StackExchangeQueryPlan("WeChat Pay API Shopify checkout", "WeChat Pay API Shopify")
    if "wechat pay" in lowered:
        return StackExchangeQueryPlan("WeChat Pay API integration", "WeChat Pay API")
    if "alipay" in lowered and "shopify" in lowered:
        return StackExchangeQueryPlan("Alipay Shopify integration", "Alipay Shopify")
    if "alipay" in lowered and "magento" in lowered:
        return StackExchangeQueryPlan("Magento Alipay integration", "Magento Alipay")
    if "alipay" in lowered and "wordpress" in lowered:
        return StackExchangeQueryPlan("WordPress Alipay payment gateway", "WordPress Alipay API")
    if "alibaba" in lowered and "api" in lowered and "order" in lowered:
        return StackExchangeQueryPlan("Alibaba API orders", "Alibaba API")
    if "alibaba" in lowered and "api" in lowered:
        return StackExchangeQueryPlan("Alibaba API integration", "Alibaba API")
    if "1688" in lowered and "api" in lowered:
        return StackExchangeQueryPlan("1688 API access", "1688 API")
    if "taobao" in lowered and "api" in lowered:
        return StackExchangeQueryPlan("Taobao API integration", "Taobao API")
    if "fapiao" in lowered and "api" in lowered:
        return StackExchangeQueryPlan("fapiao invoice API", "fapiao API")
    if "address validation" in lowered and "salesforce" in lowered:
        return StackExchangeQueryPlan("Salesforce China address validation API", "Salesforce address validation API")
    if "address validation" in lowered:
        return StackExchangeQueryPlan("China address validation API", "address validation API")
    if ("localize" in lowered or "localization" in lowered) and "saas" in lowered:
        return StackExchangeQueryPlan("Chinese SaaS localization workflow", "Chinese localization API")
    if "mini program" in lowered and ("payment" in lowered or "wechat" in lowered):
        return StackExchangeQueryPlan("WeChat mini program payment integration", "WeChat mini program API")

    return StackExchangeQueryPlan("China API integration workflow", "cross-border API integration")


def stackexchange_query_terms(query: str) -> str:
    return stackexchange_query_plan(query).strict_phrase
