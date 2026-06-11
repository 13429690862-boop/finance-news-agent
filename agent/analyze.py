"""Deterministic offline analysis from raw items to demand opportunities."""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx

from agent.models import DemandOpportunity, RawItem
from agent.ai_triage import AITriageSummary, MockCoarseTriageAnalyzer, MockFinalScoringAnalyzer
from agent.score import calculate_opportunity_score, classify_priority


DEFAULT_SCORING_CONFIG: dict[str, Any] = {
    "demand_intent_keywords": [
        "looking for",
        "need",
        "alternative",
        "problem",
        "issue",
        "help",
        "recommend",
        "supplier",
        "agent",
        "freight forwarder",
        "quality control",
        "localization",
        "api",
        "payment",
        "manufacturer",
        "source from china",
        "import from china",
    ],
    "china_relevance_keywords": [
        "china",
        "chinese",
        "alibaba",
        "1688",
        "taobao",
        "wechat",
        "alipay",
        "supplier",
        "manufacturer",
        "sourcing",
        "source from china",
        "import from china",
        "freight forwarder",
        "quality control",
    ],
    "market_intensity_high_keywords": [
        "urgent",
        "need",
        "looking for",
        "help",
        "recommend",
        "problem",
        "issue",
        "alternative",
        "supplier",
        "payment",
    ],
    "market_intensity_medium_keywords": ["checklist", "guide", "how to", "service", "support"],
    "implementation_difficulty_high_keywords": [
        "api",
        "integration",
        "platform",
        "automation",
        "compliance",
        "payment",
    ],
    "implementation_difficulty_medium_keywords": [
        "checklist",
        "guide",
        "template",
        "recommend",
        "agent",
        "quality control",
        "freight forwarder",
    ],
    "monetization_clarity_high_keywords": [
        "supplier",
        "agent",
        "freight forwarder",
        "quality control",
        "localization",
        "api",
        "payment",
        "manufacturer",
        "sourcing",
        "import",
    ],
    "monetization_clarity_medium_keywords": ["guide", "checklist", "template", "consultation"],
    "customer_type_rules": [
        {
            "keywords": ["amazon", "shopify", "ecommerce", "seller", "store"],
            "customer_type": "Ecommerce sellers and import operators",
        },
        {
            "keywords": ["freight", "forwarder", "shipping", "logistics"],
            "customer_type": "Importers managing cross-border logistics",
        },
        {
            "keywords": ["api", "integration", "software", "developer"],
            "customer_type": "Software teams integrating China-facing workflows",
        },
        {
            "keywords": ["localization", "translate", "language"],
            "customer_type": "Companies localizing products for Chinese users",
        },
        {
            "keywords": ["supplier", "manufacturer", "sourcing", "quality control", "1688", "alibaba"],
            "customer_type": "SMB buyers sourcing from China",
        },
    ],
    "risk_note_rules": {
        "default": (
            "Derived from offline fixture keyword matching only; validate with fresh, "
            "representative demand evidence before committing resources."
        )
    },
    "solution_rules": [
        {
            "keywords": ["freight", "shipping"],
            "possible_solution": "A vetted freight-forwarder matching and shipment-readiness checklist.",
            "monetization_model": "Referral fee, per-project service fee, or managed logistics coordination package.",
        },
        {
            "keywords": ["quality control"],
            "possible_solution": "A lightweight supplier quality-control coordination service.",
            "monetization_model": "Fixed-scope service package or recurring QA retainer.",
        },
        {
            "keywords": ["api"],
            "possible_solution": "A documented integration layer or API advisory package for the requested workflow.",
            "monetization_model": "Subscription, implementation fee, or paid API access.",
        },
        {
            "keywords": ["localization"],
            "possible_solution": "A localization QA package with bilingual review and market-readiness checks.",
            "monetization_model": "Fixed-scope service package or recurring QA retainer.",
        },
        {
            "keywords": ["payment"],
            "possible_solution": "A payment-readiness guide and implementation support package.",
            "monetization_model": "Paid setup support, implementation fee, or readiness checklist package.",
        },
        {
            "keywords": ["supplier", "manufacturer"],
            "possible_solution": "A curated provider shortlist plus a repeatable validation checklist.",
            "monetization_model": "Referral fee, per-project service fee, or managed sourcing package.",
        },
    ],
}


def _combined_text(item: RawItem) -> str:
    return f"{item.title}\n{item.content}".lower()


def _keywords(config: dict[str, Any], section: str) -> tuple[str, ...]:
    return tuple(str(keyword).lower() for keyword in config.get(section, []) if str(keyword).strip())


def _count_term_hits(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term in text)


def _bounded_score(base: int, hits: int, *, maximum: int = 5) -> int:
    return max(1, min(maximum, base + hits))


def _first_evidence_quote(item: RawItem) -> str:
    text = " ".join(part.strip() for part in (item.title, item.content) if part.strip())
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    keywords = ("need", "looking for", "problem", "issue", "help", "recommend", "urgent", "alternative")
    selected = next((s for s in sentences if any(k in s.lower() for k in keywords)), text)
    selected = re.sub(r"\s+", " ", selected).strip()
    if len(selected) < 20 and len(text) >= 20:
        selected = text.strip()
    selected = selected[:240]
    return selected + ("..." if len(selected) == 240 and len(text) > 240 else "")


class RuleBasedAnalyzer:
    """Offline analyzer that converts demand-like raw records into opportunities."""

    def __init__(self, scoring_config: dict[str, Any] | None = None) -> None:
        """Initialize with caller-provided scoring rules or safe built-in defaults."""
        self.scoring_config = deepcopy(scoring_config) if scoring_config is not None else deepcopy(DEFAULT_SCORING_CONFIG)

    def analyze_item(self, item: RawItem) -> DemandOpportunity | None:
        """Analyze one raw item with deterministic keyword rules."""
        text = _combined_text(item)
        demand_hits = _count_term_hits(text, _keywords(self.scoring_config, "demand_intent_keywords"))
        if demand_hits == 0:
            return None

        china_score = self._score_china_relevance(text, item)
        market_score = self._score_market_intensity(text, demand_hits)
        difficulty_score = self._score_implementation_difficulty(text)
        monetization_score = self._score_monetization_clarity(text)
        opportunity_score = calculate_opportunity_score(
            market_score,
            china_score,
            monetization_score,
            difficulty_score,
        )

        title = f"Rule-based demand: {item.title}"
        summary = (
            "Offline fixture analysis found explicit demand language around "
            f"{self._topic_label(text)}."
        )

        return DemandOpportunity(
            title=title,
            summary=summary,
            pain_point=self._pain_point(text),
            customer_type=self._classify_customer_type(text),
            possible_solution=self._possible_solution(text),
            monetization_model=self._monetization_model(text),
            evidence_urls=[item.url],
            evidence_quotes=[_first_evidence_quote(item)],
            risk_notes=self._risk_notes(),
            next_validation_step=(
                "Review at least five similar posts manually and interview two matching "
                "customer profiles about willingness to pay."
            ),
            china_relevance_score=china_score,
            market_intensity_score=market_score,
            implementation_difficulty_score=difficulty_score,
            monetization_clarity_score=monetization_score,
            opportunity_score=opportunity_score,
            priority=classify_priority(opportunity_score),
            source=item.source,
            source_type=item.source_type,
            raw_url=item.url,
        )

    def analyze_items(self, items: list[RawItem]) -> list[DemandOpportunity]:
        """Analyze many raw items, dropping generic non-demand records."""
        opportunities: list[DemandOpportunity] = []
        for item in items:
            opportunity = self.analyze_item(item)
            if opportunity is not None:
                opportunities.append(opportunity)
        return opportunities

    def _score_china_relevance(self, text: str, item: RawItem) -> int:
        terms = _keywords(self.scoring_config, "china_relevance_keywords")
        hits = _count_term_hits(text, terms)
        query_hits = _count_term_hits(item.query.lower(), terms)
        return _bounded_score(1, min(hits + query_hits, 4))

    def _score_market_intensity(self, text: str, demand_hits: int) -> int:
        punctuation_boost = 1 if re.search(r"[?!]", text) else 0
        intensity_hits = _count_term_hits(text, _keywords(self.scoring_config, "market_intensity_high_keywords"))
        return _bounded_score(1, min(demand_hits + intensity_hits + punctuation_boost, 4))

    def _score_implementation_difficulty(self, text: str) -> int:
        high_hits = _count_term_hits(text, _keywords(self.scoring_config, "implementation_difficulty_high_keywords"))
        medium_hits = _count_term_hits(text, _keywords(self.scoring_config, "implementation_difficulty_medium_keywords"))
        return max(1, min(5, 3 + high_hits - medium_hits))

    def _score_monetization_clarity(self, text: str) -> int:
        hits = _count_term_hits(text, _keywords(self.scoring_config, "monetization_clarity_high_keywords"))
        return _bounded_score(1, min(hits, 4))

    def _classify_customer_type(self, text: str) -> str:
        for rule in self.scoring_config.get("customer_type_rules", []):
            keywords = tuple(str(keyword).lower() for keyword in rule.get("keywords", []))
            if any(keyword in text for keyword in keywords):
                return str(rule.get("customer_type"))
        return "Overseas buyers with China-related operational needs"

    def _topic_label(self, text: str) -> str:
        if "freight" in text or "shipping" in text:
            return "China logistics and freight coordination"
        if "quality control" in text or "supplier" in text or "manufacturer" in text:
            return "China supplier sourcing and verification"
        if "api" in text or "integration" in text:
            return "software/API enablement"
        if "payment" in text or "alipay" in text or "wechat" in text:
            return "China payment readiness"
        if "localization" in text:
            return "localization support"
        return "a China-adjacent operational pain point"

    def _pain_point(self, text: str) -> str:
        if "alternative" in text:
            return "The user is dissatisfied with an existing option and is actively seeking a replacement."
        if "problem" in text or "issue" in text:
            return "The user reports an unresolved operational problem that may block progress."
        if "need" in text or "looking for" in text:
            return "The user states an active need and is searching for a practical provider or workflow."
        return "The user expresses demand that requires manual evaluation and follow-up."

    def _matching_solution_rule(self, text: str) -> dict[str, Any] | None:
        for rule in self.scoring_config.get("solution_rules", []):
            keywords = tuple(str(keyword).lower() for keyword in rule.get("keywords", []))
            if any(keyword in text for keyword in keywords):
                return rule
        return None

    def _possible_solution(self, text: str) -> str:
        rule = self._matching_solution_rule(text)
        if rule is not None:
            return str(rule["possible_solution"])
        return "A curated provider shortlist plus a repeatable validation checklist."

    def _monetization_model(self, text: str) -> str:
        rule = self._matching_solution_rule(text)
        if rule is not None:
            return str(rule["monetization_model"])
        return "Paid consultation, checklist template, or managed service package."

    def _risk_notes(self) -> str:
        risk_note_rules = self.scoring_config.get("risk_note_rules", {})
        if isinstance(risk_note_rules, dict):
            default = risk_note_rules.get("default")
            if isinstance(default, str) and default.strip():
                return default
        return DEFAULT_SCORING_CONFIG["risk_note_rules"]["default"]




class AITriageRuleBasedAnalyzer:
    def __init__(self, fallback: RuleBasedAnalyzer, config: dict[str, Any]):
        self.fallback = fallback
        self.config = config
        self.analyzer_mode = "rule_based"
        self.summary = AITriageSummary(enabled=bool(config.get("enabled", False)), mode="rule_based", coarse_provider=str(config.get("coarse_provider", "none")), final_provider=str(config.get("final_provider", "none")), coarse_model=str(config.get("coarse_model", "")), final_model=str(config.get("final_model", "")))
        self.coarse = MockCoarseTriageAnalyzer() if self.summary.coarse_provider == "mock_coarse" else None
        self.final = MockFinalScoringAnalyzer() if self.summary.final_provider == "mock_final" else None
        if self.summary.enabled and (self.coarse is None and self.final is None):
            self.summary.fallback_reason = "missing_or_unsupported_provider"

    def analyze_items(self, items: list[RawItem]) -> list[DemandOpportunity]:
        candidates = items
        if self.coarse is not None:
            kept = []
            for item in items:
                r = self.coarse.analyze(item)
                if r.accepted:
                    self.summary.coarse_accepted_count += 1
                    kept.append(item)
                else:
                    self.summary.coarse_rejected_count += 1
            candidates = kept
        opps = self.fallback.analyze_items(candidates)
        if self.final is not None:
            raw_by_url = {i.url: i for i in candidates}
            for o in opps:
                item = raw_by_url.get(o.raw_url)
                if item:
                    o.opportunity_score = max(o.opportunity_score, int(self.final.analyze(item).score * 10))
        self.analyzer_mode = "ai_triage_mock" if self.summary.enabled else "rule_based"
        return opps

class OpenAIAnalyzerUnavailableError(RuntimeError):
    """Raised when OpenAI analyzer cannot be initialized safely."""


class OpenAIAnalyzer:
    """Optional OpenAI-backed analyzer with per-item fallback support."""

    def __init__(self, model: str | None = None, fallback_analyzer: RuleBasedAnalyzer | None = None) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not self.api_key:
            raise OpenAIAnalyzerUnavailableError("OPENAI_API_KEY is not set; OpenAIAnalyzer is unavailable")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.fallback_analyzer = fallback_analyzer
        self.analyzer_mode = "openai_with_fallback" if fallback_analyzer is not None else "openai"
        self.prompt_template = Path("prompts/demand_analysis.md").read_text(encoding="utf-8")

    def _call_openai(self, item: RawItem) -> str:
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": self.prompt_template}]},
                {"role": "user", "content": [{"type": "input_text", "text": json.dumps(item.model_dump(), ensure_ascii=False)}]},
            ],
        }
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        return str(data.get("output_text", "")).strip()

    def _fallback(self, item: RawItem) -> DemandOpportunity | None:
        if self.fallback_analyzer is None:
            return None
        return self.fallback_analyzer.analyze_item(item)

    def analyze_item(self, item: RawItem) -> DemandOpportunity | None:
        try:
            raw = self._call_openai(item)
            parsed = json.loads(raw)
            if not parsed.get("is_real_demand", False):
                return None
            china = int(parsed["china_relevance_score"])
            market = int(parsed["market_intensity_score"])
            difficulty = int(parsed["implementation_difficulty_score"])
            monetization = int(parsed["monetization_clarity_score"])
            score = calculate_opportunity_score(market, china, monetization, difficulty)
            return DemandOpportunity(
                title=str(parsed["title"]),
                summary=str(parsed["summary"]),
                pain_point=str(parsed["pain_point"]),
                customer_type=str(parsed["customer_type"]),
                possible_solution=str(parsed["possible_solution"]),
                monetization_model=str(parsed["monetization_model"]),
                evidence_urls=[item.url],
                evidence_quotes=[str(x) for x in parsed["evidence_quotes"]],
                risk_notes=str(parsed["risk_notes"]),
                next_validation_step=str(parsed["next_validation_step"]),
                china_relevance_score=china,
                market_intensity_score=market,
                implementation_difficulty_score=difficulty,
                monetization_clarity_score=monetization,
                opportunity_score=score,
                priority=str(parsed["priority"]),
                source=item.source,
                source_type=item.source_type,
                raw_url=item.url,
            )
        except Exception:
            return self._fallback(item)

    def analyze_items(self, items: list[RawItem]) -> list[DemandOpportunity]:
        results: list[DemandOpportunity] = []
        for item in items:
            opportunity = self.analyze_item(item)
            if opportunity is not None:
                results.append(opportunity)
        return results


def build_analyzer(mode: str = "rule_based", model: str | None = None, scoring_config: dict[str, Any] | None = None, ai_triage_config: dict[str, Any] | None = None):
    triage_cfg = ai_triage_config or {}
    selected_mode = (triage_cfg.get("mode") or mode or os.getenv("ANALYZER_MODE", "rule_based")).strip().lower()
    if not bool(triage_cfg.get("enabled", False)):
        selected_mode = "rule_based"
    openai_model = model or os.getenv("OPENAI_MODEL")
    rule_based = RuleBasedAnalyzer(scoring_config=scoring_config)

    if selected_mode == "rule_based":
        rule_based.analyzer_mode = "rule_based"
        return AITriageRuleBasedAnalyzer(rule_based, triage_cfg) if triage_cfg.get("coarse_provider") == "mock_coarse" or triage_cfg.get("final_provider") == "mock_final" else rule_based

    if selected_mode == "openai":
        try:
            return OpenAIAnalyzer(model=openai_model, fallback_analyzer=rule_based)
        except OpenAIAnalyzerUnavailableError:
            rule_based.analyzer_mode = "rule_based"
            return rule_based

    if selected_mode == "auto":
        if os.getenv("OPENAI_API_KEY", "").strip():
            return OpenAIAnalyzer(model=openai_model, fallback_analyzer=rule_based)
        rule_based.analyzer_mode = "rule_based"
        return rule_based

    raise ValueError(f"Unsupported analyzer mode: {selected_mode}")
