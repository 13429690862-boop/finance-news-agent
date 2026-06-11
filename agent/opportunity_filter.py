"""Deterministic post-analysis sanity filter for opportunities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OpportunitySanityResult:
    is_valid: bool
    rejection_reasons: list[str]
    positive_reasons: list[str]


EXPLICIT_REQUEST_TERMS = (
    "looking for", "need ", "need help", "seeking", "how do i integrate", "how can i integrate",
    "how do we integrate", "can anyone recommend", "recommend a", "alternative to", "where can i find", "can someone help"
)
ACTOR_TERMS = (
    "i ", "we ", "our ", "buyer", "seller", "importer", "operator", "team", "company", "our developers", "our ecommerce", "our business", "looking for", "need "
)
DELIVERABLE_TERMS = (
    "agent", "provider", "service", "tool", "api", "integration", "supplier", "inspection", "forwarder", "workflow", "someone in china"
)
CHINA_WORKFLOW_TERMS = (
    "china sourcing", "sourcing from china", "chinese manufacturer", "chinese supplier", "factory in china",
    "import from china", "export to china", "freight forwarder china", "china freight forwarder", "china logistics",
    "customs from china", "1688", "taobao", "alibaba", "alibaba supplier", "alibaba suppliers",
    "alibaba sourcing", "alibaba api", "alibaba integration", "alibaba supplier verification",
    "verified alibaba supplier", "alibaba manufacturer", "alibaba payment", "alibaba logistics",
    "alternative to alibaba", "alibaba alternative", "wechat api", "wechat pay", "alipay",
    "chinese localization", "chinese market entry", "sell to chinese customers", "chinese ecommerce platform",
    "shenzhen supplier", "guangzhou supplier", "yiwu sourcing", "oem china", "odm china", "qc inspection china",
    "quality control china", "factory audit china", "supplier verification china", "supplier verification in china", "china supplier",
    "supplier in china", "supplier inspection", "china manufacturer", "manufacturer in china", "shipping from china", "someone in china",
    "manufacturers in shenzhen", "verified suppliers in china", "verified manufacturers in shenzhen"
)
SECURITY_NEWS_TERMS = (
    "the big hack", "tiny chip", "infiltrate", "infiltrated", "security breach", "cybersecurity",
    "supply chain hack", "supply-chain hack", "supply chain risk", "supply-chain risk", "investigative article",
    "investigation", "scandal", "bloomberg", "hardware risk"
)

PROVIDER_SIDE_TERMS = (
    "we help find factories", "we manage relationships", "we provide qc", "we offer inspections",
    "our service helps", "we handle logistics", "we can source", "we provide supplier verification",
    "we help source", "we provide factory audits", "we provide inspections"
)
GENERIC_SHOPPING_TERMS = (
    "shopping is broken", "generic shopping", "consumer goods shopping", "retail article", "ecommerce trends", "shopping behavior"
)

REJECT_TOPICS = (
    "pro-chinesecommunistparty", "politics", "tax", "nations", "ceo", "deal", "photo stories", "lewis hine",
    "resource that aims", "how everything in the world is related", "switching", "linux", "zoom", "gold seller",
    "history", "biography", "language trivia"
)


def _text(opportunity: Any, source_raw_item: Any | None) -> tuple[str, str, bool]:
    source_dict = source_raw_item if isinstance(source_raw_item, dict) else {}
    source_title = str(getattr(source_raw_item, "title", "") or source_dict.get("title", "")).lower()
    source_content = str(getattr(source_raw_item, "content", "") or source_dict.get("content", "")).lower()
    title = source_title
    has_source_primary = bool(source_title or source_content)
    return title, source_content, has_source_primary


def evaluate_opportunity_sanity(opportunity: Any, source_raw_item: Any | None = None) -> OpportunitySanityResult:
    title, content, has_source_primary = _text(opportunity, source_raw_item)
    primary = f"{title}\n{content}".strip()
    rejection: list[str] = []
    positive: list[str] = []

    if any(term in title for term in REJECT_TOPICS):
        rejection.append("non_commercial_article_or_debate_topic")
    if any(term in primary for term in ("ask hn: why", "photo stories", "global minimum corporate tax", "tim cook", "south korea switching", "france aiming to replace zoom")):
        rejection.append("known_false_positive_pattern")

    if not has_source_primary:
        rejection.extend(
            [
                "missing_source_raw_item_for_china_workflow",
                "query_metadata_not_allowed",
                "metadata_only_china_relevance",
                "no_primary_china_workflow",
            ]
        )
        return OpportunitySanityResult(
            is_valid=False, rejection_reasons=sorted(set(rejection)), positive_reasons=sorted(set(positive))
        )

    explicit_demand = any(term in primary for term in EXPLICIT_REQUEST_TERMS)
    actor = any(term in primary for term in ACTOR_TERMS)
    deliverable = any(term in primary for term in DELIVERABLE_TERMS)
    primary_customer_request = explicit_demand and actor and deliverable
    china_workflow = any(term in primary for term in CHINA_WORKFLOW_TERMS)

    if explicit_demand:
        positive.append("explicit_customer_request_in_primary_post")
    else:
        rejection.append("no_primary_customer_request")
        rejection.append("no_explicit_demand_in_title_or_primary_post")
    if actor:
        positive.append("explicit_customer_or_operator_actor")
    else:
        rejection.append("missing_explicit_customer_or_operator")
    if deliverable:
        positive.append("explicit_workflow_or_deliverable")
    else:
        rejection.append("missing_workflow_or_deliverable")

    security_news_article = any(term in primary for term in SECURITY_NEWS_TERMS)
    if security_news_article:
        rejection.append("security_news_or_scandal_article")
    if not primary_customer_request:
        rejection.append("no_primary_user_request")
        rejection.append("article_without_customer_request")

    if any(term in primary for term in GENERIC_SHOPPING_TERMS):
        rejection.append("generic_shopping_or_retail_article")

    provider_side_content = any(term in primary for term in PROVIDER_SIDE_TERMS)
    if provider_side_content and not explicit_demand:
        rejection.append("provider_side_content_not_customer_demand")
        rejection.append("no_primary_customer_request")
    market_news_article = any(term in primary for term in ("spoofing", "trader pleads guilty", "precious metals trader", "market news", "trading news"))
    if market_news_article:
        rejection.append("market_news_or_trading_article")

    if china_workflow:
        positive.append("china_specific_workflow_in_primary_post")
    else:
        rejection.append("missing_china_specific_workflow")
        rejection.append("no_primary_china_workflow")

    if "ask hn" in title and not (explicit_demand and deliverable and china_workflow):
        rejection.append("ask_hn_without_commercial_request")

    return OpportunitySanityResult(is_valid=len(rejection) == 0, rejection_reasons=sorted(set(rejection)), positive_reasons=sorted(set(positive)))
