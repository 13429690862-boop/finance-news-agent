import json

from agent.analyze import OpenAIAnalyzer, OpenAIAnalyzerUnavailableError, RuleBasedAnalyzer, build_analyzer
from agent.models import RawItem


def _raw_item():
    return RawItem(
        source="hn_algolia",
        source_type="forum_post",
        url="https://example.com/demand",
        title="Need help with China supplier search",
        content="Looking for a reliable supplier and quality control support.",
        author="u",
        published_at="2026-01-01T00:00:00Z",
        fetched_at="2026-05-18T00:00:00Z",
        query="china supplier",
        language="en",
        raw_metadata={},
    )


def test_openai_analyzer_parses_valid_json_and_preserves_provenance(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    analyzer = OpenAIAnalyzer(model="fake-model", fallback_analyzer=RuleBasedAnalyzer())

    def fake_call(item):
        return json.dumps({
            "is_real_demand": True,
            "title": "Supplier ops demand",
            "summary": "Demand detected",
            "pain_point": "Hard to find suppliers",
            "customer_type": "SMB buyers",
            "possible_solution": "Curated shortlist",
            "monetization_model": "Service fee",
            "china_relevance_score": 5,
            "market_intensity_score": 4,
            "implementation_difficulty_score": 2,
            "monetization_clarity_score": 4,
            "evidence_quotes": ["Need help with China supplier search"],
            "risk_notes": "Need more interviews",
            "next_validation_step": "Interview buyers",
            "priority": "high",
        })

    monkeypatch.setattr(analyzer, "_call_openai", fake_call)
    opp = analyzer.analyze_item(_raw_item())
    assert opp is not None
    assert opp.source == "hn_algolia"
    assert opp.source_type == "forum_post"
    assert opp.raw_url == "https://example.com/demand"


def test_openai_invalid_json_falls_back_to_rule_based(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    analyzer = OpenAIAnalyzer(fallback_analyzer=RuleBasedAnalyzer())
    monkeypatch.setattr(analyzer, "_call_openai", lambda item: "not json")
    opp = analyzer.analyze_item(_raw_item())
    assert opp is not None
    assert opp.title.startswith("Rule-based demand")


def test_build_analyzer_modes(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    a = build_analyzer(mode="rule_based")
    assert isinstance(a, RuleBasedAnalyzer)
    b = build_analyzer(mode="auto")
    assert isinstance(b, RuleBasedAnalyzer)


def test_openai_unavailable_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    try:
        OpenAIAnalyzer()
    except OpenAIAnalyzerUnavailableError:
        assert True
    else:
        assert False
