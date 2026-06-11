from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any
import re

from agent.models import RawItem


DEFAULT_QUALITY_GATE_CONFIG: dict[str, Any] = {
    "minimum_positive_groups": 2,
    "demand_intent_keywords": [
        "looking for", "need", "needs", "recommend", "recommendation", "help", "how do i", "how to", "alternative",
        "replacement", "want to buy", "want to source", "seeking", "request for", "rfq",
    ],
        "actor_keywords": [
        "buyer", "seller", "founder", "developer", "importer", "exporter", "ecommerce", "merchant", "manufacturer",
        "factory", "agency", "startup", "saas", "marketplace", "operator", "business", "company", "supplier", "customer",
    ],
    "workflow_keywords": [
        "sourcing", "logistics", "shipping", "customs", "compliance", "payment", "api integration", "localization",
        "translation", "quality control", "manufacturing", "oem", "odm", "quality inspection", "supplier verification", "factory audit",
        "cross-border", "marketplace listing", "product research", "customer support", "documentation",
    ],
    "negative_topic_keywords": [
        "election", "politics", "diplomacy", "censorship", "propaganda", "war", "military", "sanction", "tax policy",
        "historical", "dynasty", "culture", "language trivia", "geopolitics", "debate", "social media", "death",
    ],
}


@dataclass
class QualityGateResult:
    is_qualified: bool
    rejection_reasons: list[str]
    positive_signals: list[str]
    negative_signals: list[str]
    confidence: float
    source: str
    source_type: str


def _normalize_token(token: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", token.lower()).strip()


def _tokenize_text(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t}


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    hits: list[str] = []
    text_lower = text.lower()
    text_tokens = _tokenize_text(text_lower)
    for keyword in keywords:
        key = keyword.lower().strip()
        if not key:
            continue
        key_tokens = set(_normalize_token(key).split())
        if not key_tokens:
            continue
        if " " in key:
            if key in text_lower:
                hits.append(keyword)
        elif key in text_tokens:
            hits.append(keyword)
    return hits


def evaluate_raw_item_quality(item: RawItem, config: dict[str, Any] | None = None) -> QualityGateResult:
    cfg = config or DEFAULT_QUALITY_GATE_CONFIG
    text = f"{item.title}\n{item.content}".lower()
    demand_hits = _keyword_hits(text, cfg["demand_intent_keywords"])
    actor_hits = _keyword_hits(text, cfg["actor_keywords"])
    workflow_hits = _keyword_hits(text, cfg["workflow_keywords"])
    negative_hits = _keyword_hits(text, cfg["negative_topic_keywords"])

    demand_norm = {_normalize_token(k) for k in demand_hits}
    actor_unique = [k for k in actor_hits if _normalize_token(k) not in demand_norm]
    workflow_unique = [k for k in workflow_hits if _normalize_token(k) not in demand_norm and _normalize_token(k) not in {_normalize_token(a) for a in actor_unique}]
    groups = int(bool(demand_hits)) + int(bool(actor_unique)) + int(bool(workflow_unique))
    reasons: list[str] = []
    if not demand_hits:
        reasons.append("no_explicit_demand_intent")
    if not actor_unique:
        reasons.append("no_customer_actor")
    if not workflow_unique:
        reasons.append("no_deliverable_workflow")

    minimum_groups = int(cfg.get("minimum_positive_groups", 2))
    has_commercial_context = bool(demand_hits) and groups >= minimum_groups
    if negative_hits and not has_commercial_context:
        reasons.append("pure_news_or_politics")
    if ("historical" in text or "culture" in text) and not has_commercial_context:
        reasons.append("historical_or_cultural_only")
    if ("china" in text or "chinese" in text) and groups <= 1:
        reasons.append("generic_china_mention_only")

    source = item.source.lower()
    source_type = item.source_type.lower()


    if source == "stackexchange":
        stackexchange_demand_signals = [
            "how do i integrate", "how to integrate", "error integrating", "need help integrating", "api error",
            "payment gateway integration", "plugin integration", "webhook", "sdk", "authentication", "merchant account", "callback", "checkout",
        ]
        china_workflow_signals = [
            "wechat pay", "alipay", "alibaba api", "1688 api", "taobao api", "china address validation", "fapiao", "chinese localization",
        ]
        has_stackexchange_demand = any(sig in text for sig in stackexchange_demand_signals)
        has_china_workflow = any(sig in text for sig in china_workflow_signals)
        if has_stackexchange_demand and not has_china_workflow:
            reasons.append("missing_china_specific_workflow")
        if ("stock api" in text) or ("news api" in text):
            reasons.append("source_not_demand_oriented")

    if "gdelt" in source and not demand_hits:
        reasons.append("source_not_demand_oriented")
    if "hn" in source and any(x in text for x in ["politics", "debate", "geopolitics"]) and not has_commercial_context:
        reasons.append("pure_news_or_politics")

    stackexchange_blockers = ["missing_china_specific_workflow"] if source == "stackexchange" else []
    is_qualified = bool(demand_hits) and groups >= minimum_groups and not any(
        r in reasons for r in ["pure_news_or_politics", "historical_or_cultural_only", "source_not_demand_oriented", *stackexchange_blockers]
    )
    confidence = min(1.0, max(0.0, groups / 3))

    positives = [f"demand:{demand_hits[0]}" for _ in [0] if demand_hits] + [f"actor:{actor_hits[0]}" for _ in [0] if actor_hits] + [f"workflow:{workflow_hits[0]}" for _ in [0] if workflow_hits]
    return QualityGateResult(
        is_qualified=is_qualified,
        rejection_reasons=sorted(set(reasons)),
        positive_signals=positives,
        negative_signals=sorted(set(negative_hits)),
        confidence=confidence,
        source=item.source,
        source_type=item.source_type,
    )


def summarize_quality_results(results: list[tuple[RawItem, QualityGateResult]], sample_limit: int = 8) -> dict[str, Any]:
    source_counts: dict[str, dict[str, int]] = {}
    reason_counter: Counter[str] = Counter()
    rejected_samples: list[dict[str, Any]] = []

    for item, result in results:
        bucket = source_counts.setdefault(item.source, {"raw": 0, "qualified": 0, "rejected": 0})
        bucket["raw"] += 1
        if result.is_qualified:
            bucket["qualified"] += 1
        else:
            bucket["rejected"] += 1
            for reason in result.rejection_reasons:
                reason_counter[reason] += 1
            if len(rejected_samples) < sample_limit:
                rejected_samples.append({"title": item.title, "source": item.source, "rejection_reasons": result.rejection_reasons})

    return {
        "source_quality": source_counts,
        "rejection_reasons": dict(reason_counter),
        "sample_rejected_items": rejected_samples,
    }
