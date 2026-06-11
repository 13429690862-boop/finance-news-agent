from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

FORBIDDEN_BROAD_TERMS = {
    "china news",
    "china politics",
    "chinese communist party",
    "china censorship",
    "tiananmen",
    "china economy",
    "chinese culture",
    "china social media scandal",
    "general china article",
    "china business news",
    "alibaba stock news",
}

CATEGORY_SAFE_TEMPLATES = {
    "china_sourcing_agents": [
        "looking for 1688 sourcing agent",
        "need verified China supplier for Amazon FBA",
        "need supplier verification service in China",
        "looking for Shenzhen manufacturer",
        "need QC inspection before shipping from China",
        "alternative to Alibaba for verified suppliers",
    ],
    "cross_border_logistics": [
        "need China freight forwarder for small shipments",
        "DDP shipping from China for ecommerce",
        "customs clearance help importing from China",
        "shipping Alibaba order to Europe",
        "China warehouse forwarding for ecommerce",
    ],
    "china_payment_api": [
        "WeChat Pay API integration overseas",
        "Alipay payment gateway for Shopify",
        "need help integrating WeChat Pay",
        "China payment gateway for foreign company",
        "WeChat Pay merchant account overseas",
        "Alibaba payment integration for supplier orders",
    ],
    "china_localization": [
        "localize SaaS for Chinese users",
        "Chinese onboarding localization help",
        "China app store compliance support",
        "Chinese customer support workflow",
        "translate ecommerce store for Chinese market",
        "localize documentation for Chinese enterprise users",
    ],
    "china_market_entry": [
        "sell SaaS to Chinese customers",
        "China market entry help for B2B SaaS",
        "launch product in China compliance help",
        "Chinese ecommerce platform setup for overseas brand",
        "Tmall merchant setup help for overseas seller",
        "JD.com merchant setup help",
    ],
    "software_api_workflows": [
        "Alibaba API integration help",
        "1688 API access overseas",
        "Taobao API integration for orders",
        "WeChat mini program integration help",
        "Chinese address validation API",
        "fapiao invoice API integration",
    ],
}


@dataclass
class QueryAdjustmentProposal:
    scope: str
    name: str
    problem_type: str
    proposed_action: str
    proposed_query_additions: list[str]
    proposed_query_removals: list[str]
    source_profile_changes: list[str]
    rationale: str
    risk_level: str
    apply_by_default: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_safe_query_suggestion(query: str) -> bool:
    normalized = query.strip().lower()
    return bool(normalized) and all(term not in normalized for term in FORBIDDEN_BROAD_TERMS)


def generate_query_adjustment_proposals(
    recall_diagnostics: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    cfg = dict(config or {})
    if not cfg.get("enabled", True):
        return []

    max_add = int(cfg.get("max_additions_per_category", 3) or 3)
    max_remove = int(cfg.get("max_removals_per_category", 3) or 3)
    proposals: list[QueryAdjustmentProposal] = []
    for rec in (recall_diagnostics.get("source_recommendations", []) or []):
        name = str(rec.get("name", "unknown"))
        problem = str(rec.get("problem_type", "unknown"))
        if problem == "source_zero_return" and name == "stackexchange":
            proposals.append(QueryAdjustmentProposal("source", name, problem, "review_source_profile", _safe_additions("software_api_workflows", max_add), [], ["review include_categories for stackexchange and prioritize API/localization demand queries"], "source ran queries but returned zero raw items", "medium"))
        elif problem == "source_all_rejected" and name == "gdelt":
            proposals.append(QueryAdjustmentProposal("source", name, problem, "move_to_supporting", [], [], ["set gdelt as supporting-only evidence source profile"], "news-like source collected items but quality gate rejected them", "low"))
        elif problem == "high_qualified_low_final":
            proposals.append(QueryAdjustmentProposal("source", name, problem, "narrow", _safe_additions("software_api_workflows", max_add), [], [], "passed quality gate but lacked primary China workflow/request specificity", "medium"))

    for rec in (recall_diagnostics.get("category_recommendations", []) or []):
        name = str(rec.get("name", "unknown"))
        problem = str(rec.get("problem_type", "unknown"))
        if problem == "high_collected_low_qualified":
            proposals.append(QueryAdjustmentProposal("category", name, problem, "narrow", [], ["china market trends", "china business opportunities", "china ecosystem updates"][:max_remove], [], "collected raw items lacked demand intent/customer/workflow", "high"))
        elif problem == "high_qualified_low_final":
            proposals.append(QueryAdjustmentProposal("category", name, problem, "narrow", _safe_additions(name, max_add), [], [], "passed quality gate but lacked primary China workflow/request", "medium"))
        elif problem == "category_no_recall":
            proposals.append(QueryAdjustmentProposal("category", name, problem, "expand", _safe_additions(name, max_add), [], [], "category has queries but no raw recall", "medium"))
        elif problem == "category_too_broad":
            proposals.append(QueryAdjustmentProposal("category", name, problem, "narrow", _safe_additions(name, max_add), ["china updates", "china trends", "china general discussion"][:max_remove], [], "frequent no_explicit_demand_intent/no_deliverable_workflow/no_customer_actor", "high"))

    proposals.sort(key=lambda p: (_risk_rank(p.risk_level), p.scope, p.name, p.problem_type))
    return [p.to_dict() for p in proposals[:10]]


def _safe_additions(category: str, limit: int) -> list[str]:
    templates = CATEGORY_SAFE_TEMPLATES.get(category, CATEGORY_SAFE_TEMPLATES.get("software_api_workflows", []))
    return [q for q in templates if is_safe_query_suggestion(q)][:limit]


def _risk_rank(value: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(value, 9)
