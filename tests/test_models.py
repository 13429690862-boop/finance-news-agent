import pytest

from agent.models import DemandOpportunity, RawItem


def test_raw_item_accepts_required_contract_fields():
    item = RawItem(
        source="mock_forum",
        source_type="forum_post",
        url="https://example.com/item",
        title="China sourcing question",
        content="Need help finding suppliers.",
        author="fixture_user",
        published_at="2026-01-01T00:00:00Z",
        fetched_at="2026-05-18T00:00:00Z",
        query="China supplier quality control",
        language="en",
        raw_metadata={"fixture": True},
    )

    assert item.source == "mock_forum"
    assert item.raw_metadata["fixture"] is True


def _valid_opportunity_kwargs():
    return {
        "title": "Supplier QC service",
        "summary": "Overseas sellers need remote China supplier checks.",
        "pain_point": "Quality issues are found too late.",
        "china_relevance_score": 5,
        "market_intensity_score": 4,
        "implementation_difficulty_score": 2,
        "monetization_clarity_score": 4,
        "opportunity_score": 30,
        "customer_type": "Ecommerce sellers",
        "possible_solution": "Inspection coordination workflow",
        "monetization_model": "Per inspection fee",
        "evidence_urls": ["https://example.com/evidence"],
        "evidence_quotes": ["Need pre-shipment inspections"],
        "risk_notes": "Fixture only; requires real validation later.",
        "next_validation_step": "Interview five sellers.",
        "priority": "high",
    }


def test_demand_opportunity_accepts_valid_scores_priority_and_evidence():
    opportunity = DemandOpportunity(**_valid_opportunity_kwargs())

    assert opportunity.opportunity_score == 30
    assert opportunity.priority == "high"


@pytest.mark.parametrize(
    "field_name",
    [
        "china_relevance_score",
        "market_intensity_score",
        "implementation_difficulty_score",
        "monetization_clarity_score",
    ],
)
def test_demand_opportunity_rejects_factor_scores_outside_one_to_five(field_name):
    kwargs = _valid_opportunity_kwargs()
    kwargs[field_name] = 6

    with pytest.raises(ValueError):
        DemandOpportunity(**kwargs)


def test_demand_opportunity_rejects_invalid_priority():
    kwargs = _valid_opportunity_kwargs()
    kwargs["priority"] = "urgent"

    with pytest.raises(ValueError):
        DemandOpportunity(**kwargs)


def test_demand_opportunity_rejects_empty_evidence_urls():
    kwargs = _valid_opportunity_kwargs()
    kwargs["evidence_urls"] = []

    with pytest.raises(ValueError):
        DemandOpportunity(**kwargs)


def test_demand_opportunity_accepts_formula_opportunity_score_above_five():
    kwargs = _valid_opportunity_kwargs()
    kwargs["opportunity_score"] = 50

    opportunity = DemandOpportunity(**kwargs)

    assert opportunity.opportunity_score == 50
