"""Deterministic dual-track demand classification for Phase 7."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any

from agent.models import DemandClassification, QuickServiceLead, RawItem, RequesterAttribution

REQUESTER_PATTERNS: tuple[str, ...] = (
    "i need",
    "we need",
    "i'm looking for",
    "im looking for",
    "looking for",
    "seeking",
    "can someone help",
    "can anyone help",
    "need help",
    "help me",
    "help us",
    "how can i find",
    "how do i find",
    "where can i find",
    "does anyone know a service",
    "does anyone know a provider",
    "does anyone know an agent",
    "does anyone know a china",
    "does anyone know",
    "any recommendations for",
    "need a provider",
    "need an agent",
    "need someone to",
    "need consultant",
    "need a consultant",
    "need freelancer",
    "need a freelancer",
    "need service",
    "need a service",
    "our company needs",
    "my company needs",
    "small business needs",
    "trying to source",
    "trying to ship",
    "trying to integrate",
    "trying to localize",
    "trying to buy",
    "trying to purchase",
    "trying to consolidate",
)

REQUESTER_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bneed\s+(?:a\s+|an\s+)?(?:1688|taobao|alibaba|china|chinese|freight|customs|supplier|factory|qc|quality|wechat|alipay|payment|locali[sz]ation|consultant|freelancer|provider|agent|forwarder|service)\b"),
    re.compile(r"\bneed\s+(?:freight forwarder|supplier verification|chinese localization|china customs clearance|someone to|help (?:with|to|integrat|set up|source|ship|locali[sz]e|inspect|verify))"),
    re.compile(r"\b(?:i|we|our company|my company|small business)\s+need(?:s)?\b"),
)


DEMAND_SIDE_SERVICE_REQUEST_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:i|we|our company|my company|small business)\s+need(?:s)?\s+(?:a\s+|an\s+|someone\s+to\s+|someone\s+in\s+china\s+to\s+|help\s+(?:with\s+|to\s+)?|help\s+)?(?:1688|taobao|alibaba|china|chinese|freight|customs|supplier|factory|qc|quality|wechat|alipay|payment|locali[sz]ation|consultant|freelancer|provider|agent|forwarder|service|sourcing|inspection|verification|consolidat|ship|shipping|integrat|set up|setup)"),
    re.compile(r"\bneed\s+(?:a\s+|an\s+|someone\s+to\s+|someone\s+in\s+china\s+to\s+|help\s+(?:with\s+|to\s+|finding\s+(?:a\s+|an\s+)?)?|help\s+)?(?:1688|taobao|alibaba|china|chinese|freight|customs|supplier|factory|qc|quality|wechat|alipay|payment|locali[sz]ation|consultant|freelancer|provider|agent|forwarder|service|sourcing|inspection|verification|consolidat|ship|shipping|integrat|set up|setup)"),
    re.compile(r"\b(?:i|we)\s+need\s+(?:someone|somebody|a person)\s+in\s+china(?:\s+to\s+\w+)?"),
    re.compile(r"\blooking\s+for\s+(?:a\s+|an\s+)?(?:someone|somebody|person|agent|provider|service|consultant|freelancer|freight forwarder|forwarder|china customs clearance agent|sourcing agent)(?:\s+in\s+china|\s+from\s+china|\s+to\s+[^.?!,;]+)?"),
    re.compile(r"\b(?:can someone|can anyone|could someone|could anyone)\s+help(?:\s+me|\s+us)?\s+(?:integrate|set up|setup|source|ship|locali[sz]e|inspect|verify|buy|purchase|consolidate|clear|handle)"),
    re.compile(r"\b(?:where|how)\s+can\s+i\s+find\s+(?:a\s+|an\s+)?(?:reliable\s+|legit\s+|good\s+)?(?:china|chinese|1688|taobao|alibaba|freight|customs|supplier|factory|qc|quality|wechat|alipay|payment|locali[sz]ation|sourcing|inspection|verification|agent|forwarder|service)"),
    re.compile(r"\bdoes anyone know\s+(?:a\s+|an\s+)?(?:china|chinese|1688|taobao|alibaba|freight|customs|supplier|factory|qc|quality|wechat|alipay|payment|locali[sz]ation|sourcing|inspection|verification|agent|forwarder|service|provider)"),
    re.compile(r"\btrying\s+to\s+(?:source|ship|integrate|locali[sz]e|buy|purchase|consolidate)(?:\s+[^.?!,;]{0,80})?\bneed\s+(?:someone|somebody|a person|an agent|a service|help)"),
    re.compile(r"\bneed\s+(?:help\s+)?(?:with\s+|to\s+)?(?:buy|purchase|source|ship|integrate|locali[sz]e|inspect|verify|consolidate|clear|handle)\b(?:\s+[^.?!,;]{0,80})?(?:1688|taobao|alibaba|china|chinese|wechat|alipay|supplier|shipment|customs|freight)"),
)

ARTICLE_LIKE_PATTERNS: tuple[str, ...] = (
    "article about",
    "blog post about",
    "documentary",
    "story about",
    "guide to",
    "history of",
    "profile of",
    "factory tour",
    "inside the factories",
    "inside the fine art factories",
    "analysis of",
    "news about",
    "report on",
    "how to source",
    "essay",
    "photo story",
    "case study",
    "this article talks about",
    "this article describes",
    "i thought i would fill in",
)

PROVIDER_SIDE_PATTERNS: tuple[str, ...] = (
    "show hn:",
    "show hn",
    "launching",
    "product launch",
    "we built",
    "i built",
    "i made",
    "i created",
    "we provide",
    "we offer",
    "we help",
    "our company helps",
    "our company provides",
    "our services",
    "our service",
    "service provider launches",
    "provider launches",
    "choosing a china sourcing agent",
    "how to inspect suppliers",
)

PRODUCT_LAUNCH_PATTERNS: tuple[str, ...] = (
    "show hn:",
    "launch hn:",
    "ask hn:",
    "i built",
    "we built",
    "my co-founder and i built",
    "my cofounder and i built",
    "i launched",
    "we launched",
    "announcing",
    "introducing",
    "our product",
    "our app",
    "product launch",
    "beta launch",
    "new app",
    "saas launch",
    "startup launch",
)

SERVICE_WORKFLOWS: dict[str, tuple[str, ...]] = {
    "1688/Taobao/Alibaba buying support": ("1688", "taobao", "alibaba", "buy from china", "purchase from china"),
    "sourcing agent": ("sourcing agent", "source from china", "sourcing from china", "contact supplier", "supplier sourcing"),
    "supplier verification": ("supplier verification", "verify supplier", "supplier audit", "factory audit", "manufacturer verification", "supplier in shenzhen", "shenzhen supplier"),
    "QC inspection": ("qc inspection", "quality control", "inspect supplier", "supplier inspection", "inspect shipment", "inspection before shipment", "pre shipment inspection"),
    "freight forwarding / customs": ("freight forwarder", "freight forwarding", "ddp shipping", "customs clearance", "ship from china", "shipping from china", "china to us", "china to usa"),
    "WeChat Pay / Alipay integration": ("wechat pay", "alipay", "china payment", "payment integration"),
    "Chinese localization / support": ("chinese localization", "mandarin localization", "localize", "localization", "chinese customer support", "saas onboarding"),
    "China workflow setup": ("someone in china", "person in china", "china app", "china-facing", "china facing", "fapiao", "chinese invoice", "china address validation", "yiwu", "shenzhen", "manufacturer workflow"),
}

DELIVERABLE_PATTERNS: tuple[str, ...] = (
    "help set up",
    "set up",
    "integrate",
    "verify",
    "verification",
    "source",
    "inspect",
    "inspection",
    "ship",
    "translate",
    "localize",
    "contact supplier",
    "purchase",
    "order",
    "handle documentation",
    "someone in china",
    "person in china",
    "buying agent",
    "agent",
    "forwarder",
    "customs",
    "support",
    "help",
)

BLOCKED_PATTERNS: dict[str, tuple[str, ...]] = {
    "identity_or_kyc_evasion": ("kyc bypass", "bypass kyc", "avoid kyc", "identity verification bypass", "fake id", "fake identity"),
    "fake_or_sold_accounts": ("fake account", "create fake", "buy wechat account", "sell wechat account", "wechat account for sale", "buy alipay account", "account selling"),
    "payment_fraud": ("payment fraud", "stolen card", "chargeback fraud", "launder", "money mule"),
    "credential_sharing": ("share credentials", "sell credentials", "password sharing", "login credentials"),
    "sanctions_or_export_evasion": ("sanctions evasion", "evade sanctions", "export control evasion", "bypass export controls"),
    "illegal_or_regulated_goods": ("counterfeit", "illegal goods", "drugs", "weapons", "firearms", "controlled substance"),
    "impersonation": ("impersonate", "pretend to be", "act as someone else"),
    "private_data_scraping": ("scrape private data", "private personal data", "harvest emails", "scrape phone numbers"),
    "spam_or_seo_outreach": ("mass spam", "seo outreach", "bulk outreach", "cold email blast"),
}

SENSITIVE_PATTERNS: dict[str, tuple[str, ...]] = {
    "account_or_payment_setup_requires_compliance_review": ("open wechat pay", "setup wechat pay", "set up wechat pay", "open alipay", "setup alipay", "set up alipay", "payment account", "merchant account", "china bank account"),
    "customs_or_regulated_trade_review": ("customs", "import license", "export license", "regulated", "ddp"),
}

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")


def source_primary_text(item: RawItem) -> str:
    """Return source-primary evidence text; metadata/query/category are intentionally excluded."""
    return " ".join(part.strip() for part in (item.title, item.content) if part and part.strip())


def _redact_sensitive_public_contact(text: str) -> str:
    redacted = _EMAIL_RE.sub("[redacted-public-email]", text)
    redacted = _PHONE_RE.sub("[redacted-public-phone]", redacted)
    return redacted


def _excerpt(item: RawItem, limit: int = 220) -> str:
    text = _redact_sensitive_public_contact(re.sub(r"\s+", " ", source_primary_text(item)).strip())
    return text[: limit - 1] + "…" if len(text) > limit else text


def _contains_any(text: str, patterns: tuple[str, ...]) -> list[str]:
    return [pattern for pattern in patterns if pattern in text]


def _requester_matches(text: str) -> list[str]:
    """Return generic requester/request language from source-primary text only."""
    hits = _contains_any(text, REQUESTER_PATTERNS)
    regex_hits = [regex.pattern for regex in REQUESTER_REGEXES if regex.search(text)]
    return [*hits, *regex_hits]


def _demand_side_service_request_matches(text: str) -> list[str]:
    """Return explicit customer-side requests for a service/action, not provider launch copy."""
    return [regex.pattern for regex in DEMAND_SIDE_SERVICE_REQUEST_REGEXES if regex.search(text)]


def _is_news_or_article_source(item: RawItem) -> bool:
    source = (item.source or "").lower()
    source_type = (item.source_type or "").lower()
    return source == "gdelt" or source_type in {"news", "article", "blog"}


def _workflow_matches(text: str) -> tuple[str, list[str]]:
    matches: list[tuple[str, list[str]]] = []
    for service, terms in SERVICE_WORKFLOWS.items():
        hits = _contains_any(text, terms)
        if hits:
            matches.append((service, hits))
    if not matches:
        return "", []
    service, hits = sorted(matches, key=lambda row: len(row[1]), reverse=True)[0]
    return service, hits


def _compliance_assessment(text: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    for reason, terms in BLOCKED_PATTERNS.items():
        if _contains_any(text, terms):
            reasons.append(reason)
    if reasons:
        return "blocked", reasons

    for reason, terms in SENSITIVE_PATTERNS.items():
        if _contains_any(text, terms):
            reasons.append(reason)
    if any("account_or_payment" in reason for reason in reasons):
        return "high", reasons
    if reasons:
        return "medium", reasons
    return "low", []


def extract_requester_attribution(item: RawItem) -> RequesterAttribution:
    """Extract only public requester/source metadata already present on the raw item."""
    metadata = item.raw_metadata or {}
    source = (item.source or "").lower()
    display_name = ""
    handle = ""
    profile_url = ""
    source_id = ""
    platform = item.source or "unknown"
    confidence = "unknown"
    contact_method = "unknown"
    notes = "Requester not available from public source metadata; no identity inference performed."

    if source == "hn_algolia":
        author = str(item.author or "").strip()
        if author:
            display_name = author
            handle = author
            profile_url = f"https://news.ycombinator.com/user?id={author}"
            source_id = str(metadata.get("objectID") or metadata.get("story_id") or "")
            confidence = "high"
            contact_method = "profile_only"
            notes = "HN author was provided by Algolia public metadata; profile URL is derived from the public HN username."
    elif source == "stackexchange":
        owner = metadata.get("owner") if isinstance(metadata.get("owner"), dict) else {}
        display_name = str(owner.get("display_name") or item.author or "").strip()
        handle = display_name
        profile_url = str(owner.get("link") or "").strip()
        source_id = str(owner.get("user_id") or metadata.get("question_id") or "")
        if display_name or profile_url or source_id:
            confidence = "high"
            contact_method = "profile_only" if profile_url else "source_reply_only"
            notes = "StackExchange owner fields came from public API metadata."
    elif source == "gdelt" or item.source_type.lower() == "news":
        platform = "gdelt"
        notes = "News/supporting source; requester is unknown/not_applicable unless source-primary text is a direct request."

    return RequesterAttribution(
        requester_display_name=display_name or "unknown",
        requester_handle=handle or "unknown",
        requester_profile_url=profile_url,
        requester_platform=platform,
        requester_source_id=source_id,
        source_url=item.url,
        public_metadata_only=True,
        attribution_confidence=confidence,
        evidence_excerpt=_excerpt(item),
        contact_allowed=False,
        contact_method=contact_method,
        notes=notes,
    )


def classify_demand(item: RawItem) -> DemandClassification:
    text = source_primary_text(item).lower()
    compliance_risk, compliance_reasons = _compliance_assessment(text)
    requester_hits = _requester_matches(text)
    demand_service_request_hits = _demand_side_service_request_matches(text)
    service, workflow_hits = _workflow_matches(text)
    deliverable_hits = _contains_any(text, DELIVERABLE_PATTERNS)
    article_hits = _contains_any(text, ARTICLE_LIKE_PATTERNS)
    provider_hits = _contains_any(text, PROVIDER_SIDE_PATTERNS)
    product_launch_hits = _contains_any(text, PRODUCT_LAUNCH_PATTERNS)
    reasons: list[str] = []
    if requester_hits:
        reasons.append("source_primary_requester_signal")
    if demand_service_request_hits:
        reasons.append("demand_side_service_request_signal")
    if workflow_hits:
        reasons.append("source_primary_china_workflow_signal")
    if deliverable_hits:
        reasons.append("source_primary_deliverable_signal")
    if article_hits:
        reasons.append("article_like_content")
    if provider_hits:
        reasons.append("provider_side_content")
    if product_launch_hits:
        reasons.append("product_launch_content")
        if any(hit in product_launch_hits for hit in ("i built", "we built", "my co-founder and i built", "my cofounder and i built", "i launched", "we launched")):
            reasons.append("maker_self_promotion")
    if _is_news_or_article_source(item):
        reasons.append("news_or_article_source_not_direct_requester")
    if compliance_risk == "blocked":
        return DemandClassification(track="rejected", confidence=0.0, classification_reasons=reasons + ["compliance_blocked"], compliance_risk="blocked", compliance_reasons=compliance_reasons)
    non_customer_request_reasons: list[str] = []
    if product_launch_hits:
        non_customer_request_reasons.append("product_launch_without_customer_request")
    if "maker_self_promotion" in reasons:
        non_customer_request_reasons.append("maker_self_promotion_without_customer_request")
    if provider_hits:
        non_customer_request_reasons.append("provider_side_without_customer_request")
    if article_hits:
        non_customer_request_reasons.append("article_without_service_request")
    if non_customer_request_reasons and not demand_service_request_hits:
        return DemandClassification(
            track="supporting_evidence",
            confidence=0.25,
            classification_reasons=reasons + non_customer_request_reasons + ["no_explicit_service_request"],
            compliance_risk=compliance_risk,
            compliance_reasons=compliance_reasons,
        )
    if _is_news_or_article_source(item):
        return DemandClassification(track="supporting_evidence", confidence=0.25 if workflow_hits else 0.0, classification_reasons=reasons + ["not_demand_side_requester_source"], compliance_risk=compliance_risk, compliance_reasons=compliance_reasons)
    if demand_service_request_hits and workflow_hits and deliverable_hits:
        confidence = min(0.95, 0.55 + 0.08 * min(len(demand_service_request_hits) + len(workflow_hits) + len(deliverable_hits), 5))
        return DemandClassification(track="quick_service_lead", confidence=confidence, classification_reasons=reasons, compliance_risk=compliance_risk, compliance_reasons=compliance_reasons)
    if workflow_hits:
        rejection_reason = "no_explicit_service_request" if not demand_service_request_hits else "missing_deliverable_signal"
        return DemandClassification(track="supporting_evidence", confidence=0.35, classification_reasons=reasons + [rejection_reason], compliance_risk=compliance_risk, compliance_reasons=compliance_reasons)
    return DemandClassification(track="rejected", confidence=0.0, classification_reasons=reasons or ["missing_source_primary_quick_service_evidence", "no_explicit_service_request"], compliance_risk=compliance_risk, compliance_reasons=compliance_reasons)


def _lead_id(item: RawItem) -> str:
    stable = f"{item.source}|{item.url}|{item.title}"
    return "qsl_" + hashlib.sha1(stable.encode("utf-8")).hexdigest()[:12]


def _score(text: str, high_terms: tuple[str, ...], base: int = 2) -> int:
    return max(1, min(5, base + len(_contains_any(text, high_terms))))


def build_quick_service_lead(item: RawItem) -> QuickServiceLead | None:
    classification = classify_demand(item)
    if classification.track != "quick_service_lead":
        return None
    text = source_primary_text(item).lower()
    requested_service, _ = _workflow_matches(text)
    compliance_prefix = "Manual compliance review; only provide legitimate guidance. " if classification.compliance_risk in {"medium", "high"} else ""
    return QuickServiceLead(
        lead_id=_lead_id(item),
        title=item.title,
        demand_summary=_excerpt(item, limit=180),
        requested_service=requested_service or "China workflow support",
        source=item.source,
        source_url=item.url,
        requester=extract_requester_attribution(item),
        urgency_score=_score(text, ("urgent", "asap", "before shipment", "need", "looking for"), base=1),
        simplicity_score=_score(text, ("buying agent", "verify", "inspect", "translate", "localize", "freight forwarder", "check"), base=2),
        monetization_score=_score(text, ("small business", "company", "shopify", "supplier", "shipment", "integration", "customs", "ddp"), base=2),
        compliance_risk=classification.compliance_risk,
        compliance_reasons=classification.compliance_reasons,
        suggested_service_offer=_suggested_offer(requested_service, classification.compliance_risk),
        suggested_next_step=compliance_prefix + "Manually review the public source thread/profile context; do not auto-contact or infer identity.",
        evidence_excerpt=_excerpt(item),
        raw_item_id=str((item.raw_metadata or {}).get("objectID") or (item.raw_metadata or {}).get("question_id") or item.url),
        published_at=item.published_at,
        created_at=item.published_at,
        classification=classification,
    )


def _suggested_offer(requested_service: str, compliance_risk: str) -> str:
    if compliance_risk in {"medium", "high"}:
        return "Compliance-reviewed advisory call and legitimate implementation checklist only."
    if "freight" in requested_service.lower() or "customs" in requested_service.lower():
        return "Fixed-scope freight/customs coordination triage and provider shortlist."
    if "verification" in requested_service.lower() or "inspection" in requested_service.lower() or "qc" in requested_service.lower():
        return "Supplier verification or pre-shipment inspection coordination package."
    if "payment" in requested_service.lower() or "alipay" in requested_service.lower() or "wechat" in requested_service.lower():
        return "Payment integration readiness review and compliant setup guidance."
    if "localization" in requested_service.lower():
        return "Bilingual localization QA and China onboarding support package."
    return "Manual China workflow support package with clear scope, compliance screen, and no private-data collection."


def classify_quick_service_leads(items: list[RawItem]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    leads: list[dict[str, Any]] = []
    blocked_or_rejected: list[dict[str, Any]] = []
    for item in items:
        classification = classify_demand(item)
        if classification.track == "quick_service_lead":
            lead = build_quick_service_lead(item)
            if lead is not None:
                leads.append(lead.model_dump())
        elif classification.compliance_risk == "blocked" or any(
            reason in classification.classification_reasons
            for reason in (
                "article_without_service_request",
                "no_explicit_service_request",
                "provider_side_without_customer_request",
                "product_launch_without_customer_request",
                "maker_self_promotion_without_customer_request",
                "not_demand_side_requester_source",
            )
        ):
            blocked_or_rejected.append({
                "source": item.source,
                "source_url": item.url,
                "title": item.title,
                "track": classification.track,
                "compliance_risk": classification.compliance_risk,
                "compliance_reasons": classification.compliance_reasons,
                "classification_reasons": classification.classification_reasons,
                "evidence_excerpt": _excerpt(item),
            })
    leads.sort(key=lambda row: (row.get("monetization_score", 0), row.get("urgency_score", 0), row.get("simplicity_score", 0)), reverse=True)
    return leads, blocked_or_rejected


def summarize_quick_service_leads(leads: list[dict[str, Any]], blocked: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    blocked = blocked or []
    blocked_count = len([record for record in blocked if record.get("compliance_risk") == "blocked"])
    article_count = sum(1 for record in blocked if "article_without_service_request" in (record.get("classification_reasons") or []))
    no_request_count = sum(1 for record in blocked if "no_explicit_service_request" in (record.get("classification_reasons") or []))
    provider_count = sum(1 for record in blocked if "provider_side_without_customer_request" in (record.get("classification_reasons") or []))
    product_launch_count = sum(1 for record in blocked if "product_launch_without_customer_request" in (record.get("classification_reasons") or []))
    accepted_count = len(leads)
    return {
        "total": accepted_count,
        "candidate_count": accepted_count + len(blocked),
        "accepted_count": accepted_count,
        "rejected_article_like_count": article_count,
        "rejected_no_explicit_request_count": no_request_count,
        "rejected_provider_side_count": provider_count,
        "rejected_product_launch_count": product_launch_count,
        "quick_service_rejected_article_count": article_count,
        "quick_service_rejected_no_request_count": no_request_count,
        "quick_service_rejected_provider_side_count": provider_count,
        "quick_service_rejected_product_launch_count": product_launch_count,
        "high_monetization_count": sum(1 for lead in leads if int(lead.get("monetization_score", 0) or 0) >= 4),
        "high_compliance_risk_count": sum(1 for lead in leads if lead.get("compliance_risk") in {"high", "blocked"}),
        "blocked_count": blocked_count + sum(1 for lead in leads if lead.get("compliance_risk") == "blocked"),
        "by_source": dict(Counter(str(lead.get("source", "unknown")) for lead in leads)),
        "by_requested_service": dict(Counter(str(lead.get("requested_service", "unknown")) for lead in leads)),
    }


def summarize_requester_attribution(leads: list[dict[str, Any]]) -> dict[str, Any]:
    by_platform: Counter[str] = Counter()
    with_public = 0
    unknown = 0
    for lead in leads:
        requester = lead.get("requester", {}) if isinstance(lead.get("requester"), dict) else {}
        platform = str(requester.get("requester_platform") or lead.get("source") or "unknown")
        by_platform[platform] += 1
        if requester.get("attribution_confidence") in {"high", "medium"} and requester.get("requester_display_name") != "unknown":
            with_public += 1
        else:
            unknown += 1
    return {"with_public_requester": with_public, "unknown_requester": unknown, "by_platform": dict(by_platform)}


def summarize_compliance(leads: list[dict[str, Any]], blocked: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    blocked = blocked or []
    counts = Counter(str(lead.get("compliance_risk", "low")) for lead in leads)
    counts["blocked"] += len(blocked)
    reasons: Counter[str] = Counter()
    for record in [*leads, *blocked]:
        for reason in record.get("compliance_reasons", []) or []:
            reasons[str(reason)] += 1
    return {"low": counts.get("low", 0), "medium": counts.get("medium", 0), "high": counts.get("high", 0), "blocked": counts.get("blocked", 0), "reasons": dict(reasons)}


def product_opportunity_records(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for opportunity in opportunities:
        record = dict(opportunity)
        record["track"] = "product_opportunity"
        record["product_opportunity_score"] = record.get("opportunity_score", record.get("score", 0))
        record["repeated_demand_score"] = record.get("market_intensity_score", 0)
        record["market_signal_score"] = record.get("weighted_score", record.get("opportunity_score", 0))
        record["source_evidence_count"] = record.get("evidence_count", len(record.get("evidence_urls", []) or []))
        record["supporting_sources"] = record.get("evidence_urls", [])
        record["risks"] = record.get("risk_notes", "")
        record["suggested_validation_next_step"] = record.get("next_validation_step", "Validate with repeated source-primary demand evidence.")
        records.append(record)
    return records
