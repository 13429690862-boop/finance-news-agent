from agent.sources.stackexchange import StackExchangeCollector
from agent.sources.stackexchange import stackexchange_query_plan, stackexchange_query_terms


def _question(**overrides):
    base = {
        "question_id": 123,
        "title": "How to support China payment methods?",
        "link": "https://stackoverflow.com/questions/123",
        "tags": ["payments", "china"],
        "owner": {"display_name": "alice"},
        "creation_date": 1714521600,
        "score": 5,
        "answer_count": 2,
    }
    base.update(overrides)
    return base


def test_successful_response_maps_items_to_raw_items():
    collector = StackExchangeCollector()
    collector._fetch_questions = lambda query, max_items, site: {"items": [_question()]}

    items = collector.collect(["china payments"], max_items=10)

    assert len(items) == 1
    assert items[0].source == "stackexchange"
    assert items[0].source_type == "qa"
    assert items[0].url == "https://stackoverflow.com/questions/123"
    assert items[0].title == "How to support China payment methods?"
    assert items[0].author == "alice"
    assert items[0].query == "china payments"


def test_max_items_is_respected():
    collector = StackExchangeCollector()
    collector._fetch_questions = lambda query, max_items, site: {
        "items": [_question(question_id=i, link=f"https://stackoverflow.com/questions/{i}") for i in range(10)]
    }

    items = collector.collect(["a", "b"], max_items=3)

    assert len(items) == 3


def test_missing_owner_fallback_works():
    collector = StackExchangeCollector()
    collector._fetch_questions = lambda query, max_items, site: {"items": [_question(owner=None)]}

    items = collector.collect(["china"], max_items=10)

    assert len(items) == 1
    assert items[0].author == ""


def test_missing_optional_fields_fallback_works():
    collector = StackExchangeCollector()
    collector._fetch_questions = lambda query, max_items, site: {
        "items": [_question(tags=None, creation_date=None, answer_count=None, score=None)]
    }

    items = collector.collect(["china"], max_items=10)

    assert len(items) == 1
    assert items[0].published_at == ""
    assert items[0].content == "How to support China payment methods? | 123"


def test_malformed_response_fails_gracefully():
    collector = StackExchangeCollector()
    collector._fetch_questions = lambda query, max_items, site: {"items": "not-a-list"}

    items = collector.collect(["china"], max_items=10)

    assert items == []


def test_http_error_or_exception_fails_gracefully():
    collector = StackExchangeCollector()

    def _boom(query, max_items, site):
        raise RuntimeError("boom")

    collector._fetch_questions = _boom
    items = collector.collect(["china"], max_items=10)
    assert items == []


def test_empty_items_returns_empty_list():
    collector = StackExchangeCollector()
    collector._fetch_questions = lambda query, max_items, site: {"items": []}

    items = collector.collect(["china"], max_items=10)

    assert items == []


def test_multisite_dedupes_and_partial_failure():
    collector = StackExchangeCollector(sites=["stackoverflow", "webmasters"])
    def _fetch(query, max_items, site):
        if site == "webmasters":
            raise RuntimeError("boom")
        return {"items": [_question(), _question()]}
    collector._fetch_questions = _fetch
    items = collector.collect(["WeChat Pay API integration overseas"], max_items=10)
    assert len(items) == 1


def test_stackexchange_query_terms_rewrites_to_technical_search_terms():
    assert stackexchange_query_terms("WeChat Pay API integration overseas") == "WeChat Pay API integration"
    assert stackexchange_query_terms("Alipay payment gateway for Shopify") == "Alipay Shopify integration"
    assert stackexchange_query_terms("Alibaba API integration help") == "Alibaba API integration"
    assert stackexchange_query_terms("localize SaaS for Chinese users") == "Chinese SaaS localization workflow"


def test_stackexchange_query_plan_has_safe_technical_fallbacks():
    plan = stackexchange_query_plan("WeChat Pay API integration overseas")
    assert plan.strict_phrase == "WeChat Pay API integration"
    assert plan.fallback_phrase == "WeChat Pay API"

    plan = stackexchange_query_plan("Alipay payment gateway for Shopify")
    assert plan.strict_phrase == "Alipay Shopify integration"
    assert plan.fallback_phrase == "Alipay Shopify"

    plan = stackexchange_query_plan("Alibaba API integration help")
    assert plan.strict_phrase == "Alibaba API integration"
    assert plan.fallback_phrase == "Alibaba API"


def test_stackexchange_query_terms_avoid_broad_standalone_terms():
    blocked = {"China", "Alibaba", "payment", "localization", "supplier", "ecommerce", "news", "politics"}
    for query in ["China", "Alibaba", "payment", "localization", "Chinese market"]:
        assert stackexchange_query_terms(query) not in blocked


def test_stackexchange_fallback_never_returns_forbidden_broad_standalone_term():
    forbidden = {"china", "alibaba", "payment", "localization", "supplier", "ecommerce", "news", "politics"}
    for query in [
        "WeChat Pay API integration overseas",
        "Alipay payment gateway for Shopify",
        "Alibaba API integration help",
        "1688 API access overseas",
        "Taobao API integration for orders",
        "fapiao invoice API integration",
    ]:
        plan = stackexchange_query_plan(query)
        assert plan.fallback_phrase.strip().lower() not in forbidden
