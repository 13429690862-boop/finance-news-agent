from agent.ai_triage import MockCoarseTriageAnalyzer, MockFinalScoringAnalyzer, ai_provider_dry_run_check
from agent.models import RawItem


def _item(title: str, content: str, query: str = "china"):
    return RawItem(source="hn_algolia", source_type="forum_post", url=f"https://e/{title}", title=title, content=content, author="a", published_at="2026-01-01T00:00:00Z", fetched_at="2026-01-02T00:00:00Z", query=query, language="en", raw_metadata={})


def test_mock_coarse_rejects_obvious_noise():
    r = MockCoarseTriageAnalyzer().analyze(_item("JP Morgan spoofing", "trading spoof"))
    assert r.accepted is False


def test_mock_coarse_keeps_true_demand():
    r = MockCoarseTriageAnalyzer().analyze(_item("Need 1688 sourcing agent", "need supplier help"))
    assert r.accepted is True


def test_mock_final_scores_true_demand_higher_than_noise():
    a = MockFinalScoringAnalyzer()
    hi = a.analyze(_item("Need WeChat Pay API integration", "api integration request")).score
    lo = a.analyze(_item("Generic shopping article", "shopping deals")).score
    assert hi > lo


def test_ai_provider_check_disabled_returns_skipped():
    r = ai_provider_dry_run_check({"dry_run_provider_check": False})
    assert r["provider_check_status"] == "skipped"
    assert r["used_for_opportunity_qualification"] is False


def test_ai_provider_check_missing_secrets_returns_skipped():
    r = ai_provider_dry_run_check({"dry_run_provider_check": True})
    assert r["provider_check_status"] == "skipped"
    assert "COARSE_AI_API_KEY" in r["missing_secrets"]
