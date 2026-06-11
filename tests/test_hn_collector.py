from agent.sources.hn import HNAlgoliaCollector


def _hit(**overrides):
    base = {
        "objectID": "123",
        "title": "Need better China payments tooling",
        "story_title": None,
        "story_url": "https://example.com/story",
        "comment_text": "Teams need support for Alipay and WeChat Pay",
        "story_text": None,
        "author": "alice",
        "created_at": "2026-05-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_successful_response_maps_hits_to_raw_items():
    collector = HNAlgoliaCollector()
    collector._fetch_hits = lambda query: {"hits": [_hit()]}

    items = collector.collect(["china payments"], max_items=10)

    assert len(items) == 1
    assert items[0].source == "hn_algolia"
    assert items[0].source_type == "discussion"
    assert items[0].url == "https://example.com/story"
    assert items[0].title == "Need better China payments tooling"
    assert items[0].query == "china payments"


def test_max_items_is_respected():
    collector = HNAlgoliaCollector()
    collector._fetch_hits = lambda query: {"hits": [_hit(objectID=str(i), story_url=f"https://example.com/{i}") for i in range(5)]}

    items = collector.collect(["a", "b"], max_items=3)

    assert len(items) == 3


def test_missing_story_url_falls_back_to_hn_item_url():
    collector = HNAlgoliaCollector()
    collector._fetch_hits = lambda query: {"hits": [_hit(story_url=None, objectID="999")]}

    items = collector.collect(["china"], max_items=10)

    assert len(items) == 1
    assert items[0].url == "https://news.ycombinator.com/item?id=999"


def test_malformed_response_fails_gracefully():
    collector = HNAlgoliaCollector()
    collector._fetch_hits = lambda query: {"hits": "not-a-list"}

    items = collector.collect(["china"], max_items=10)

    assert items == []


def test_http_error_fails_gracefully():
    collector = HNAlgoliaCollector()

    def _boom(query):
        raise RuntimeError("boom")

    collector._fetch_hits = _boom
    items = collector.collect(["china"], max_items=10)
    assert items == []


def test_empty_hits_returns_empty_list():
    collector = HNAlgoliaCollector()
    collector._fetch_hits = lambda query: {"hits": []}

    items = collector.collect(["china"], max_items=10)

    assert items == []
