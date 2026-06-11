from agent.models import RawItem
from agent.quality_gate import DEFAULT_QUALITY_GATE_CONFIG, evaluate_raw_item_quality


def mk(title: str, content: str, source: str = "hn_algolia", source_type: str = "forum_post", query: str = "china") -> RawItem:
    return RawItem(source=source, source_type=source_type, url="https://x", title=title, content=content, author="a", published_at="2026-01-01T00:00:00Z", fetched_at="2026-01-01T00:00:00Z", query=query, language="en", raw_metadata={})


def test_accepts_1688_sourcing():
    r = evaluate_raw_item_quality(mk("Need 1688 sourcing agent", "I am a buyer and need supplier verification and logistics help"))
    assert r.is_qualified


def test_rejects_political_news_gdelt():
    r = evaluate_raw_item_quality(mk("China politics debate", "geopolitics and censorship news", source="gdelt", source_type="news"))
    assert not r.is_qualified
    assert "pure_news_or_politics" in r.rejection_reasons


def test_accepts_wechat_api_integration_stackexchange():
    r = evaluate_raw_item_quality(mk("WeChat API integration help", "Developer needs payment API integration for ecommerce app", source="stackexchange", source_type="qa"))
    assert r.is_qualified


def test_stackexchange_question_like_china_workflow_passes():
    r = evaluate_raw_item_quality(mk("How do I integrate WeChat Pay API in Shopify checkout?", "Need help integrating merchant account callback for WeChat Pay checkout", source="stackexchange", source_type="qa"))
    assert r.is_qualified


def test_stackexchange_generic_payment_rejects_without_china_context():
    r = evaluate_raw_item_quality(mk("How to accept payments?", "Need help integrating a payment gateway", source="stackexchange", source_type="qa"))
    assert not r.is_qualified
    assert "missing_china_specific_workflow" in r.rejection_reasons


def test_stackexchange_generic_stock_or_news_api_rejects():
    assert not evaluate_raw_item_quality(mk("Alibaba stock API", "Need stock price API", source="stackexchange", source_type="qa")).is_qualified
    assert not evaluate_raw_item_quality(mk("China news API", "Looking for a news API for headlines", source="stackexchange", source_type="qa")).is_qualified


def test_query_text_cannot_qualify_news_article():
    r = evaluate_raw_item_quality(
        mk(
            "Global minimum corporate tax: 130 nations to support U.S. proposal",
            "Macro policy update and diplomatic reactions.",
            source="gdelt",
            source_type="news",
            query="China sourcing supplier importer workflow help",
        )
    )
    assert not r.is_qualified


def test_query_text_cannot_qualify_generic_china_article():
    r = evaluate_raw_item_quality(
        mk(
            "Apple CEO Tim Cook secretly signed $275B deal with China",
            "Corporate news analysis without buyer request.",
            query="China sourcing help for importer",
        )
    )
    assert not r.is_qualified


def test_single_keyword_cannot_satisfy_multiple_groups():
    assert not evaluate_raw_item_quality(mk("China payment system update", "Market update only.")).is_qualified
    assert not evaluate_raw_item_quality(mk("China supplier market update", "Industry overview.")).is_qualified


def test_explicit_demand_actor_workflow_qualifies():
    assert evaluate_raw_item_quality(mk("Looking for a China payment API integration provider for ecommerce checkout", "Need a provider for ecommerce payment integration workflow")).is_qualified
    assert evaluate_raw_item_quality(mk("Need a 1688 sourcing agent for Amazon FBA imports", "I am an importer looking for sourcing and logistics support")).is_qualified


def test_real_report_false_positive_examples_rejected():
    titles = [
        "Ask HN: Why is HN predominated by pro-ChineseCommunistParty people?",
        "Lewis Hine's early 20th-century photo stories",
        "System – A resource that aims to explain how everything in the world is related",
        "South Korea switching their PCs to Linux",
    ]
    for title in titles:
        result = evaluate_raw_item_quality(mk(title, "General discussion and news context."))
        assert not result.is_qualified, title


def test_custom_config_can_change_behavior():
    cfg = dict(DEFAULT_QUALITY_GATE_CONFIG)
    cfg["minimum_positive_groups"] = 3
    result = evaluate_raw_item_quality(
        mk("Need supplier support", "Need supplier help", query="ignore me"),
        cfg,
    )
    assert not result.is_qualified
