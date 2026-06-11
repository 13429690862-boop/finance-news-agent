from agent.models import DemandOpportunity, RawItem
from agent.opportunity_filter import evaluate_opportunity_sanity


def _raw(title: str, content: str = "") -> RawItem:
    return RawItem(source="hn_algolia", source_type="forum_post", url="https://x", title=title, content=content, author="a", published_at="2026-01-01T00:00:00Z", fetched_at="2026-05-18T00:00:00Z", query="china", language="en", raw_metadata={})


def _opp(title: str, evidence_quotes: list[str] | None = None) -> DemandOpportunity:
    return DemandOpportunity(title=title, summary="s", pain_point="p", customer_type="c", possible_solution="sol", monetization_model="m", evidence_urls=["https://x"], evidence_quotes=evidence_quotes or ["need supplier help"], risk_notes="r", next_validation_step="n", china_relevance_score=4, market_intensity_score=4, implementation_difficulty_score=2, monetization_clarity_score=4, opportunity_score=32, priority="high", source="hn_algolia", source_type="forum_post", raw_url="https://x")


def test_false_positive_examples_rejected():
    titles = [
        "Ask HN: Why is HN predominated by pro-ChineseCommunistParty people?",
        "Lewis Hine’s early 20th-century photo stories",
        "Global minimum corporate tax: 130 nations to support U.S. proposal",
        "Apple CEO Tim Cook 'secretly' signed $275B deal with China",
        "System – A resource that aims to explain how everything in the world is related",
        "South Korea switching their 3.3M PCs to Linux",
        "France Aiming to Replace Zoom",
        "Tales from a non-Chinese Gold Seller",
    ]
    for t in titles:
        assert not evaluate_opportunity_sanity(_opp(t), _raw(t)).is_valid


def test_remaining_false_positives_rejected():
    for title in [
        "Parable of the Sofa",
        "Ask HN: Any Internet retailers of physical goods here?",
    ]:
        result = evaluate_opportunity_sanity(_opp(title), _raw(title, "General retail/business discussion"))
        assert not result.is_valid
        assert "missing_china_specific_workflow" in result.rejection_reasons


def test_generic_variants_rejected_without_china_context():
    pairs = [
        ("Any ecommerce retailers doing well this year?", "We are discussing generic internet retail trends"),
        ("Modern manufacturing bottlenecks", "Need suppliers but no China workflow details"),
        ("Payment API failures on checkout", "Need payment retries with Stripe only"),
    ]
    for title, content in pairs:
        result = evaluate_opportunity_sanity(_opp(title), _raw(title, content))
        assert not result.is_valid
        assert "missing_china_specific_workflow" in result.rejection_reasons


def test_generic_supplier_qc_terms_rejected_without_china_context():
    for title in ["Need supplier QC process help", "Need supplier quality control checklist"]:
        result = evaluate_opportunity_sanity(_opp(title), _raw(title, "Need a QA checklist for supplier quality"))
        assert not result.is_valid
        assert "missing_china_specific_workflow" in result.rejection_reasons


def test_comment_only_china_does_not_qualify():
    result = evaluate_opportunity_sanity(
        _opp("Ask HN: Any Internet retailers of physical goods here?", evidence_quotes=["Try importing from China suppliers"]),
        _raw("Ask HN: Any Internet retailers of physical goods here?", "General retail discussion only"),
    )
    assert not result.is_valid
    assert "missing_china_specific_workflow" in result.rejection_reasons


def test_missing_source_raw_item_rejected_for_china_workflow():
    result = evaluate_opportunity_sanity(_opp("China sourcing help"), None)
    assert not result.is_valid
    assert "missing_source_raw_item_for_china_workflow" in result.rejection_reasons
    assert "query_metadata_not_allowed" in result.rejection_reasons
    assert "metadata_only_china_relevance" in result.rejection_reasons


def test_analyzer_generated_china_title_does_not_qualify_without_primary_evidence():
    result = evaluate_opportunity_sanity(
        _opp("Need supplier verification in China"),
        _raw("Need supplier verification help", "Need a supplier verification process for global vendors"),
    )
    assert not result.is_valid
    assert "missing_china_specific_workflow" in result.rejection_reasons


def test_e3_false_positives_are_rejected_even_with_demand_metadata():
    bad_items = [
        (
            "Hunter Becomes the Prey - shopping is broken",
            "General shopping behavior discussion without explicit China workflow request.",
        ),
        (
            "Another ex-JP Morgan precious metals trader pleads guilty to ‘spoofing’",
            "Financial market news and trading enforcement update.",
        ),
    ]
    for title, content in bad_items:
        raw = RawItem(
            source="hn_algolia",
            source_type="forum_post",
            url="https://x",
            title=title,
            content=content,
            author="a",
            published_at="2026-01-01T00:00:00Z",
            fetched_at="2026-05-18T00:00:00Z",
            query="how to find Chinese manufacturer",
            query_category="china_sourcing_agents",
            source_profile="demand_high_precision",
            language="en",
            raw_metadata={},
        )
        opp = DemandOpportunity(
            title="Need verified manufacturer in Shenzhen",
            summary="China-facing summary generated by analyzer",
            pain_point="p",
            customer_type="SMB importing from China",
            possible_solution="China sourcing workflow automation",
            monetization_model="m",
            evidence_urls=["https://x"],
            evidence_quotes=["Need a China supplier workflow"],
            risk_notes="r",
            next_validation_step="n",
            china_relevance_score=5,
            market_intensity_score=4,
            implementation_difficulty_score=2,
            monetization_clarity_score=4,
            opportunity_score=32,
            priority="high",
            source="hn_algolia",
            source_type="forum_post",
            raw_url="https://x",
        )
        result = evaluate_opportunity_sanity(opp, raw)
        assert not result.is_valid
        assert "no_primary_user_request" in result.rejection_reasons
        assert "article_without_customer_request" in result.rejection_reasons
        assert "missing_china_specific_workflow" in result.rejection_reasons


def test_query_category_or_source_profile_cannot_qualify_generic_item():
    raw = _raw("Generic retail trends", "General ecommerce trends and market commentary.")
    raw.query_category = "china_payment_api"
    raw.source_profile = "demand_high_precision"
    result = evaluate_opportunity_sanity(_opp("Need WeChat Pay API integration"), raw)
    assert not result.is_valid
    assert "missing_china_specific_workflow" in result.rejection_reasons


def test_explicit_demand_examples_pass():
    pairs = [
        ("Looking for a 1688 sourcing agent for Amazon FBA", "We need a sourcing agent for repeat orders"),
        ("Need a China freight forwarder for small shipments", "Our ecommerce team needs a forwarder"),
        ("How do I integrate WeChat Pay API for overseas ecommerce?", "Our developers need API integration guidance"),
        ("Looking for verified manufacturers in Shenzhen", "Need supplier verification before contract"),
        ("Need QC inspection before shipping from China", "We are importers needing inspection workflow"),
        ("Need supplier verification in China", "Need supplier verification in China before placing orders"),
        ("Alternative to Alibaba for verified suppliers", "Need a vetted supplier discovery workflow"),
        ("Looking for Alibaba supplier verification service", "Need help vetting suppliers and onboarding workflow"),
        ("Need help integrating Alibaba API for supplier orders", "Our team needs Alibaba integration for supplier ordering"),
    ]
    for title, content in pairs:
        assert evaluate_opportunity_sanity(_opp(title), _raw(title, content)).is_valid


def test_bare_alibaba_news_rejected():
    for title in ["Alibaba stock price news", "Alibaba signs new partnership"]:
        result = evaluate_opportunity_sanity(_opp(title), _raw(title, "market update and news summary"))
        assert not result.is_valid


def test_security_news_and_scandal_articles_rejected_without_customer_request():
    titles = [
        "The Big Hack: How China Used a Tiny Chip to Infiltrate Amazon and Apple",
        "China used a tiny chip to infiltrate Amazon and Apple",
        "supply chain hack news involving China",
        "security breach article about China",
        "generic cybersecurity news about Chinese hardware",
        "Bloomberg-style investigative article about China supply chain risk",
    ]
    for title in titles:
        result = evaluate_opportunity_sanity(_opp(title), _raw(title, "Investigative security report about supply chain risk"))
        assert not result.is_valid
        assert "security_news_or_scandal_article" in result.rejection_reasons
        assert "article_without_customer_request" in result.rejection_reasons
        assert "no_primary_user_request" in result.rejection_reasons


def test_provider_side_article_rejected_without_customer_request():
    title = "The Factory Floor: Picking (and Maintaining) a Partner"
    content = "We help find factories, we manage relationships, we provide QC, we offer inspections, and we handle logistics in China."
    result = evaluate_opportunity_sanity(_opp(title), _raw(title, content))
    assert not result.is_valid
    assert "provider_side_content_not_customer_demand" in result.rejection_reasons
    assert "no_primary_customer_request" in result.rejection_reasons


def test_generic_shopping_article_rejected_even_with_chinaish_metadata_words():
    title = "Hunter Becomes the Prey - shopping is broken"
    content = "Shopping is broken for consumer goods. Importers and ecommerce operators discuss workflow issues in general."
    result = evaluate_opportunity_sanity(_opp("Need China supplier workflow"), _raw(title, content))
    assert not result.is_valid
    assert "generic_shopping_or_retail_article" in result.rejection_reasons
    assert "no_primary_customer_request" in result.rejection_reasons
