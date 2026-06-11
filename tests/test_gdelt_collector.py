from agent.sources.gdelt import GDELTCollector


def _article(**overrides):
    base = {
        "title": "China logistics bottlenecks create SaaS demand",
        "url": "https://example.com/news-1",
        "source": "Example News",
        "seendate": "2026-05-01T00:00:00Z",
        "snippet": "SMBs are asking for tracking automation",
        "domain": "example.com",
        "language": "English",
    }
    base.update(overrides)
    return base


def test_successful_response_maps_results_to_raw_items():
    collector = GDELTCollector()
    collector._fetch_articles = lambda query, max_items: {"articles": [_article()]}

    items = collector.collect(["china logistics"], max_items=10)

    assert len(items) == 1
    assert items[0].source == "gdelt"
    assert items[0].source_type == "news"
    assert items[0].url == "https://example.com/news-1"
    assert items[0].title == "China logistics bottlenecks create SaaS demand"
    assert items[0].query == "china logistics"


def test_max_items_is_respected():
    collector = GDELTCollector()
    collector._fetch_articles = lambda query, max_items: {
        "articles": [_article(title=f"title-{i}", url=f"https://example.com/{i}") for i in range(5)]
    }

    items = collector.collect(["a", "b"], max_items=3)

    assert len(items) == 3


def test_missing_optional_fields_fallback_works():
    collector = GDELTCollector()
    collector._fetch_articles = lambda query, max_items: {
        "articles": [_article(source=None, snippet=None, domain="fallback.example")]
    }

    items = collector.collect(["china"], max_items=10)

    assert len(items) == 1
    assert items[0].author == ""
    assert items[0].content == "China logistics bottlenecks create SaaS demand | fallback.example"


def test_malformed_response_fails_gracefully():
    collector = GDELTCollector()
    collector._fetch_articles = lambda query, max_items: {"articles": "not-a-list"}

    items = collector.collect(["china"], max_items=10)

    assert items == []


def test_http_error_fails_gracefully():
    collector = GDELTCollector()

    def _boom(query, max_items):
        raise RuntimeError("boom")

    collector._fetch_articles = _boom
    items = collector.collect(["china"], max_items=10)
    assert items == []


def test_empty_results_returns_empty_list():
    collector = GDELTCollector()
    collector._fetch_articles = lambda query, max_items: {"articles": []}

    items = collector.collect(["china"], max_items=10)

    assert items == []
