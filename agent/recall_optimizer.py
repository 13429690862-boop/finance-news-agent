from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

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
}

DEMAND_QUERY_TEMPLATES = {
    "china_sourcing_agents": [
        "looking for 1688 sourcing agent",
        "need verified China supplier for Amazon FBA",
        "how to find factory in Shenzhen",
        "need supplier verification service in China",
        "QC inspection before shipping from China",
    ],
    "cross_border_logistics": [
        "need freight forwarder from China to US",
        "DDP shipping from China for small business",
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
    ],
    "china_localization": [
        "localize SaaS for Chinese users",
        "Chinese onboarding localization help",
        "China app store compliance support",
        "Chinese customer support workflow",
        "translate ecommerce store for Chinese market",
    ],
    "software_api_workflows": [
        "Alibaba API integration help",
        "1688 API access overseas",
        "Taobao API integration for orders",
        "WeChat mini program integration help",
        "Chinese address validation API",
    ],
}

BROAD_REASON_TRIGGERS = {
    "no_explicit_demand_intent",
    "no_deliverable_workflow",
    "no_customer_actor",
    "generic_china_mention_only",
}


@dataclass
class RecallDiagnostic:
    scope: str
    name: str
    problem_type: str
    severity: str
    evidence: str
    recommended_action: str
    rationale: str


CategoryRecommendation = RecallDiagnostic
SourceRecommendation = RecallDiagnostic


def _as_int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _row(r: RecallDiagnostic) -> dict[str, Any]:
    return asdict(r)


def build_recall_diagnostics(telemetry: Mapping[str, Any]) -> dict[str, Any]:
    source_recs = [_row(r) for r in _source_recommendations(telemetry)]
    category_recs = [_row(r) for r in _category_recommendations(telemetry)]
    query_suggestions = build_query_suggestions(telemetry, category_recs)
    return {
        "source_recommendations": source_recs,
        "category_recommendations": category_recs,
        "query_suggestions": query_suggestions,
    }


def _source_recommendations(telemetry: Mapping[str, Any]) -> list[SourceRecommendation]:
    out: list[SourceRecommendation] = []
    for name, bucket in (telemetry.get("source_telemetry", {}) or {}).items():
        collected = _as_int(bucket.get("collected_count"))
        qualified = _as_int(bucket.get("qualified_raw_count"))
        final_q = _as_int(bucket.get("final_qualified_count"))
        query_count = _as_int(bucket.get("query_count"))
        stype = str(bucket.get("source_type", "")).lower()
        if query_count > 0 and collected == 0:
            out.append(SourceRecommendation("source", name, "source_zero_return", "high", f"query_count={query_count}, collected_count=0", "review_source_profile", "Queries executed but source returned zero raw items; review source profile/query fit."))
        if collected > 0 and qualified == 0:
            action = "move_to_supporting" if stype == "news" or name == "gdelt" else "narrow"
            rationale = "Collected items were rejected by quality gate; keep strict gate and adjust source role or queries."
            if name == "stackexchange":
                action = "needs_query_narrowing"
                rationale = "StackExchange collector is operational but items were quality-rejected; prioritize explicit API/integration demand phrasing."
            out.append(SourceRecommendation("source", name, "source_all_rejected", "high", f"collected_count={collected}, qualified_raw_count=0", action, rationale))
        if qualified > 0 and final_q == 0:
            out.append(SourceRecommendation("source", name, "high_qualified_low_final", "medium", f"qualified_raw_count={qualified}, final_qualified_count=0", "needs_query_narrowing", "Qualified candidates failed final opportunity filter; use more explicit demand/workflow phrasing."))
        if stype == "news":
            out.append(SourceRecommendation("source", name, "supporting_source_only", "low", f"source_type={stype}", "move_to_supporting", "News-like source should remain supporting evidence, not primary demand discovery."))
    return sorted(out, key=lambda r: (SEVERITY_ORDER.get(r.severity, 9), r.scope, r.name, r.problem_type))


def _category_recommendations(telemetry: Mapping[str, Any]) -> list[CategoryRecommendation]:
    out: list[CategoryRecommendation] = []
    for name, bucket in (telemetry.get("category_telemetry", {}) or {}).items():
        collected = _as_int(bucket.get("collected_count"))
        qualified = _as_int(bucket.get("qualified_raw_count"))
        final_q = _as_int(bucket.get("final_qualified_count"))
        query_count = _as_int(bucket.get("query_count"))
        reasons = set((bucket.get("rejection_reason_counts", {}) or {}).keys())
        if query_count > 0 and collected == 0:
            out.append(CategoryRecommendation("category", name, "category_no_recall", "high", f"query_count={query_count}, collected_count=0", "needs_query_expansion", "Category has no raw recall; expand demand-oriented phrasing or revise source profile."))
        if collected > 0 and qualified == 0:
            out.append(CategoryRecommendation("category", name, "high_collected_low_qualified", "high", f"collected_count={collected}, qualified_raw_count=0", "narrow", "Collected items lacked quality-gate signals; narrow to explicit demand/workflow requests."))
        if qualified > 0 and final_q == 0:
            out.append(CategoryRecommendation("category", name, "high_qualified_low_final", "medium", f"qualified_raw_count={qualified}, final_qualified_count=0", "narrow", "Category produced candidates but final filter found no opportunity-grade demand."))
        if reasons.intersection(BROAD_REASON_TRIGGERS):
            out.append(CategoryRecommendation("category", name, "category_too_broad", "medium", f"top_reasons={','.join(sorted(reasons.intersection(BROAD_REASON_TRIGGERS)))}", "needs_query_narrowing", "Frequent broad/no-demand rejection reasons indicate this category should use explicit user-request language."))
    return sorted(out, key=lambda r: (SEVERITY_ORDER.get(r.severity, 9), r.scope, r.name, r.problem_type))


def build_query_suggestions(telemetry: Mapping[str, Any], category_recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    action_by_category = {r["name"]: r["recommended_action"] for r in category_recommendations}
    out: list[dict[str, Any]] = []
    for category, templates in DEMAND_QUERY_TEMPLATES.items():
        action = action_by_category.get(category, "keep")
        if action == "needs_query_expansion":
            action = "expand"
        elif action == "needs_query_narrowing" or action == "narrow":
            action = "narrow"
        out.append({"category": category, "suggested_action": action, "suggested_queries": [q for q in templates if q.strip().lower() not in FORBIDDEN_BROAD_TERMS]})
    return out
