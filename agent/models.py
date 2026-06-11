"""Shared data contracts for source ingestion and opportunity scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.util import find_spec
from typing import Any, Literal


_SCORE_FIELDS = {
    "china_relevance_score",
    "market_intensity_score",
    "implementation_difficulty_score",
    "monetization_clarity_score",
    "opportunity_score",
}
_VALID_PRIORITIES = {"high", "medium", "low"}
_VALID_TRACKS = {"quick_service_lead", "product_opportunity", "supporting_evidence", "rejected"}
_VALID_RISKS = {"low", "medium", "high", "blocked"}


if find_spec("pydantic") is not None:
    from pydantic import BaseModel, Field, field_validator

    class RawItem(BaseModel):
        """Raw overseas demand signal collected from an offline or external source."""

        source: str
        source_type: str
        url: str
        title: str
        content: str
        author: str
        published_at: str
        fetched_at: str
        query: str
        language: str
        query_category: str | None = None
        source_profile: str | None = None
        raw_metadata: dict[str, Any] = Field(default_factory=dict)

    class DemandClassification(BaseModel):
        """Deterministic dual-track classification attached to source-primary demand evidence."""

        track: Literal["quick_service_lead", "product_opportunity", "supporting_evidence", "rejected"]
        confidence: float = Field(ge=0, le=1)
        classification_reasons: list[str] = Field(default_factory=list)
        compliance_risk: Literal["low", "medium", "high", "blocked"]
        compliance_reasons: list[str] = Field(default_factory=list)
        source_primary_evidence_required: bool = True

    class RequesterAttribution(BaseModel):
        """Public requester/source metadata; never inferred beyond source API fields."""

        requester_display_name: str = "unknown"
        requester_handle: str = "unknown"
        requester_profile_url: str = ""
        requester_platform: str = "unknown"
        requester_source_id: str = ""
        source_url: str = ""
        public_metadata_only: bool = True
        attribution_confidence: Literal["high", "medium", "low", "unknown"] = "unknown"
        evidence_excerpt: str = ""
        contact_allowed: bool = False
        contact_method: Literal["source_reply_only", "profile_only", "unknown"] = "unknown"
        notes: str = ""

    class QuickServiceLead(BaseModel):
        """Individual/small-business demand that may be handled manually without market proof."""

        lead_id: str
        title: str
        demand_summary: str
        requested_service: str
        source: str
        source_url: str
        requester: RequesterAttribution
        urgency_score: int = Field(ge=1, le=5)
        simplicity_score: int = Field(ge=1, le=5)
        monetization_score: int = Field(ge=1, le=5)
        compliance_risk: Literal["low", "medium", "high", "blocked"]
        compliance_reasons: list[str] = Field(default_factory=list)
        suggested_service_offer: str
        suggested_next_step: str
        evidence_excerpt: str
        raw_item_id: str = ""
        created_at: str = ""
        published_at: str = ""
        classification: DemandClassification

    class ProductOpportunity(BaseModel):
        """Track-B product opportunity wrapper preserving existing opportunity fields."""

        track: Literal["product_opportunity"] = "product_opportunity"
        title: str
        product_opportunity_score: float = Field(ge=0)
        repeated_demand_score: int | float = 0
        market_signal_score: int | float = 0
        source_evidence_count: int = 0
        supporting_sources: list[str] = Field(default_factory=list)
        risks: str = ""
        suggested_validation_next_step: str = ""

    class DemandOpportunity(BaseModel):
        """Normalized opportunity candidate derived from one or more raw signals."""

        title: str
        summary: str
        pain_point: str
        china_relevance_score: int = Field(ge=1, le=5)
        market_intensity_score: int = Field(ge=1, le=5)
        implementation_difficulty_score: int = Field(ge=1, le=5)
        monetization_clarity_score: int = Field(ge=1, le=5)
        opportunity_score: float = Field(ge=1)
        customer_type: str
        possible_solution: str
        monetization_model: str
        evidence_urls: list[str]
        evidence_quotes: list[str]
        risk_notes: str
        next_validation_step: str
        priority: Literal["high", "medium", "low"]
        source: str | None = None
        source_type: str | None = None
        raw_url: str | None = None

        @field_validator("evidence_urls")
        @classmethod
        def evidence_urls_must_not_be_empty(cls, value: list[str]) -> list[str]:
            if not value:
                raise ValueError("evidence_urls must not be empty")
            return value

else:

    @dataclass
    class RawItem:
        """Raw overseas demand signal collected from an offline or external source."""

        source: str
        source_type: str
        url: str
        title: str
        content: str
        author: str
        published_at: str
        fetched_at: str
        query: str
        language: str
        query_category: str | None = None
        source_profile: str | None = None
        raw_metadata: dict[str, Any] = field(default_factory=dict)

        def model_dump(self) -> dict[str, Any]:
            return self.__dict__.copy()

    @dataclass
    class DemandClassification:
        """Deterministic dual-track classification attached to source-primary demand evidence."""

        track: str
        confidence: float
        classification_reasons: list[str] = field(default_factory=list)
        compliance_risk: str = "low"
        compliance_reasons: list[str] = field(default_factory=list)
        source_primary_evidence_required: bool = True

        def __post_init__(self) -> None:
            if self.track not in _VALID_TRACKS:
                raise ValueError("invalid demand track")
            if not 0 <= self.confidence <= 1:
                raise ValueError("confidence must be between 0 and 1")
            if self.compliance_risk not in _VALID_RISKS:
                raise ValueError("invalid compliance risk")

        def model_dump(self) -> dict[str, Any]:
            return self.__dict__.copy()

    @dataclass
    class RequesterAttribution:
        """Public requester/source metadata; never inferred beyond source API fields."""

        requester_display_name: str = "unknown"
        requester_handle: str = "unknown"
        requester_profile_url: str = ""
        requester_platform: str = "unknown"
        requester_source_id: str = ""
        source_url: str = ""
        public_metadata_only: bool = True
        attribution_confidence: str = "unknown"
        evidence_excerpt: str = ""
        contact_allowed: bool = False
        contact_method: str = "unknown"
        notes: str = ""

        def model_dump(self) -> dict[str, Any]:
            return self.__dict__.copy()

    @dataclass
    class QuickServiceLead:
        """Individual/small-business demand that may be handled manually without market proof."""

        lead_id: str
        title: str
        demand_summary: str
        requested_service: str
        source: str
        source_url: str
        requester: RequesterAttribution
        urgency_score: int
        simplicity_score: int
        monetization_score: int
        compliance_risk: str
        compliance_reasons: list[str]
        suggested_service_offer: str
        suggested_next_step: str
        evidence_excerpt: str
        raw_item_id: str = ""
        created_at: str = ""
        published_at: str = ""
        classification: DemandClassification | None = None

        def __post_init__(self) -> None:
            for name in ("urgency_score", "simplicity_score", "monetization_score"):
                value = getattr(self, name)
                if value < 1 or value > 5:
                    raise ValueError(f"{name} must be between 1 and 5")
            if self.compliance_risk not in _VALID_RISKS:
                raise ValueError("invalid compliance risk")

        def model_dump(self) -> dict[str, Any]:
            data = self.__dict__.copy()
            if self.requester is not None:
                data["requester"] = self.requester.model_dump()
            if self.classification is not None:
                data["classification"] = self.classification.model_dump()
            return data

    @dataclass
    class ProductOpportunity:
        """Track-B product opportunity wrapper preserving existing opportunity fields."""

        title: str
        product_opportunity_score: float
        repeated_demand_score: int | float = 0
        market_signal_score: int | float = 0
        source_evidence_count: int = 0
        supporting_sources: list[str] = field(default_factory=list)
        risks: str = ""
        suggested_validation_next_step: str = ""
        track: str = "product_opportunity"

        def model_dump(self) -> dict[str, Any]:
            return self.__dict__.copy()

    @dataclass
    class DemandOpportunity:
        """Normalized opportunity candidate derived from one or more raw signals."""

        title: str
        summary: str
        pain_point: str
        china_relevance_score: int
        market_intensity_score: int
        implementation_difficulty_score: int
        monetization_clarity_score: int
        opportunity_score: float
        customer_type: str
        possible_solution: str
        monetization_model: str
        evidence_urls: list[str]
        evidence_quotes: list[str]
        risk_notes: str
        next_validation_step: str
        priority: str
        source: str | None = None
        source_type: str | None = None
        raw_url: str | None = None

        def __post_init__(self) -> None:
            for field_name in _SCORE_FIELDS:
                value = getattr(self, field_name)
                if value < 1:
                    raise ValueError(f"{field_name} must be at least 1")
                if field_name != "opportunity_score" and value > 5:
                    raise ValueError(f"{field_name} must be between 1 and 5")
            if self.priority not in _VALID_PRIORITIES:
                raise ValueError("priority must be high, medium, or low")
            if not self.evidence_urls:
                raise ValueError("evidence_urls must not be empty")

        def model_dump(self) -> dict[str, Any]:
            return self.__dict__.copy()
