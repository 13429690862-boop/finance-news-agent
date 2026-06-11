from agent.analyze import RuleBasedAnalyzer
from agent.config import load_scoring_config
from agent.models import DemandOpportunity, RawItem


def _raw_item(title="Need China supplier quality control", content="Looking for help with a supplier issue in China."):
    return RawItem(
        source="mock_forum",
        source_type="forum_post",
        url="https://example.com/item",
        title=title,
        content=content,
        author="fixture_user",
        published_at="2026-01-01T00:00:00Z",
        fetched_at="2026-05-18T00:00:00Z",
        query="China supplier quality control",
        language="en",
        raw_metadata={"fixture": True},
    )


def test_rule_based_analyzer_returns_opportunity_for_demand_like_raw_item():
    opportunity = RuleBasedAnalyzer().analyze_item(_raw_item())

    assert isinstance(opportunity, DemandOpportunity)
    assert opportunity.evidence_urls == ["https://example.com/item"]
    assert opportunity.china_relevance_score >= 4
    assert opportunity.priority in {"high", "medium", "low"}


def test_rule_based_analyzer_returns_none_for_generic_content():
    item = _raw_item(
        title="A general overview of Canton Fair history",
        content="This article summarizes exhibition dates and background information.",
    )

    assert RuleBasedAnalyzer().analyze_item(item) is None


def test_rule_based_analyzer_works_with_scoring_config():
    config = load_scoring_config("configs/scoring.yaml")
    opportunity = RuleBasedAnalyzer(scoring_config=config).analyze_item(
        _raw_item(
            title="Need WeChat API problem help",
            content="Looking for WeChat API integration help for Chinese payment workflow.",
        )
    )

    assert opportunity is not None
    assert opportunity.customer_type == "Software teams integrating China-facing workflows"
    assert "API" in opportunity.possible_solution


def test_scoring_heuristics_are_deterministic_and_use_formula():
    opportunity = RuleBasedAnalyzer().analyze_item(
        _raw_item(
            title="Need China freight forwarder and payment help!",
            content="Looking for a China freight forwarder alternative because payment and shipping are a problem.",
        )
    )

    assert opportunity is not None
    assert opportunity.china_relevance_score == 5
    assert opportunity.market_intensity_score == 5
    assert opportunity.monetization_clarity_score >= 3
    assert opportunity.implementation_difficulty_score >= 1
    assert opportunity.opportunity_score == (
        opportunity.market_intensity_score
        * opportunity.china_relevance_score
        * opportunity.monetization_clarity_score
        / opportunity.implementation_difficulty_score
    )


def test_analyze_items_filters_generic_items_and_preserves_batch_order():
    demand_item = _raw_item(title="Need a 1688 agent", content="Looking for payment help and supplier messages.")
    generic_item = _raw_item(title="China trade fair photos", content="A gallery of booth pictures.")

    opportunities = RuleBasedAnalyzer().analyze_items([generic_item, demand_item])

    assert len(opportunities) == 1
    assert opportunities[0].evidence_urls == [demand_item.url]


def test_rule_based_analyzer_preserves_source_fields():
    item = _raw_item()
    item.source = "gdelt"
    item.source_type = "news"
    item.url = "https://example.com/news"
    opportunity = RuleBasedAnalyzer().analyze_item(item)
    assert opportunity is not None
    assert opportunity.source == "gdelt"
    assert opportunity.source_type == "news"
    assert opportunity.raw_url == "https://example.com/news"
