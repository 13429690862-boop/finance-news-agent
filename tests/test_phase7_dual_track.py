import json

from agent.demand_classifier import build_quick_service_lead, classify_demand, classify_quick_service_leads, extract_requester_attribution
from agent.models import RawItem
from agent.pipeline import run_fixture_pipeline
from agent.report import generate_json_summary, generate_markdown_report


def raw(title, content="", source="hn_algolia", url="https://news.ycombinator.com/item?id=1", author="alice", metadata=None, source_type="discussion"):
    return RawItem(
        source=source,
        source_type=source_type,
        url=url,
        title=title,
        content=content or title,
        author=author,
        published_at="2026-01-01T00:00:00Z",
        fetched_at="2026-05-29T00:00:00Z",
        query="china workflow demand",
        language="en",
        raw_metadata=metadata or {"objectID": "1"},
    )


def test_quick_service_positive_examples():
    examples = [
        "I need a 1688 buying agent to purchase samples",
        "Looking for someone in China to inspect supplier before shipment",
        "Need freight forwarder from China to US for small business",
        "Can someone help integrate WeChat Pay for Shopify?",
        "Need Chinese localization help for SaaS onboarding",
        "Need supplier verification in Shenzhen before we order",
    ]
    for idx, text in enumerate(examples):
        item = raw(text, url=f"https://news.ycombinator.com/item?id={idx}")
        classification = classify_demand(item)
        assert classification.track == "quick_service_lead"
        lead = build_quick_service_lead(item)
        assert lead is not None
        assert lead.classification.source_primary_evidence_required is True
        assert lead.requester.contact_allowed is False


def test_short_user_phrases_are_quick_service_leads():
    examples = [
        ("I need a sourcing agent", "sourcing agent"),
        ("Looking for someone in China", "China workflow setup"),
        ("Can someone help me integrate WeChat Pay", "WeChat Pay / Alipay integration"),
        ("Where can I find a freight forwarder", "freight forwarding / customs"),
        ("Our company needs supplier inspection", "QC inspection"),
    ]
    for idx, (text, requested_service) in enumerate(examples):
        item = raw(text, url=f"https://news.ycombinator.com/item?id=short-{idx}")
        classification = classify_demand(item)
        assert classification.track == "quick_service_lead", text
        assert "source_primary_requester_signal" in classification.classification_reasons
        assert "source_primary_china_workflow_signal" in classification.classification_reasons
        assert "source_primary_deliverable_signal" in classification.classification_reasons
        lead = build_quick_service_lead(item)
        assert lead is not None
        assert lead.requested_service == requested_service

def test_product_opportunity_repeated_patterns_still_report_as_product_track(tmp_path):
    opportunities = [
        {"title": "Repeated China payment integration pain", "priority": "high", "opportunity_score": 20, "market_intensity_score": 5, "evidence_urls": ["https://a.example"]},
        {"title": "Repeated sourcing agent demand", "priority": "medium", "opportunity_score": 15, "market_intensity_score": 4, "evidence_urls": ["https://b.example"]},
        {"title": "Repeated DDP shipping demand", "priority": "low", "opportunity_score": 10, "market_intensity_score": 3, "evidence_urls": ["https://c.example"]},
    ]
    output = tmp_path / "summary.json"
    generate_json_summary(opportunities, output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["product_opportunity_summary"]["total"] == 3
    assert all(row["track"] == "product_opportunity" for row in payload["product_opportunities"])
    assert payload["opportunities"][0]["track"] == "product_opportunity"


def test_reject_and_block_bad_or_non_request_content():
    blocked = [
        "Need help with fake account creation for WeChat",
        "Looking for KYC bypass for Alipay merchant account",
        "Need to buy WeChat accounts in bulk",
        "Need help with payment fraud using Alipay",
        "Can someone share credentials for a supplier portal",
    ]
    for text in blocked:
        classification = classify_demand(raw(text))
        assert classification.track == "rejected"
        assert classification.compliance_risk == "blocked"

    negatives = [
        "China manufacturing news article says exports rose",
        "This article describes Alibaba earnings without a customer request",
        "I mentioned China in a comment but do not need anything",
        "We offer service for China sourcing and freight forwarding",
    ]
    for text in negatives:
        classification = classify_demand(raw(text, author=""))
        assert classification.track != "quick_service_lead"


def test_ambiguous_payment_account_request_is_high_risk_not_evasion():
    item = raw("We need help set up WeChat Pay merchant account for Shopify checkout")
    lead = build_quick_service_lead(item)
    assert lead is not None
    assert lead.compliance_risk == "high"
    assert "Manual compliance review" in lead.suggested_next_step
    assert "bypass" not in lead.suggested_next_step.lower()


def test_requester_attribution_public_metadata_only():
    hn = extract_requester_attribution(raw("Need supplier verification in Shenzhen", author="pg", metadata={"objectID": "42"}))
    assert hn.requester_handle == "pg"
    assert hn.requester_profile_url == "https://news.ycombinator.com/user?id=pg"
    assert hn.attribution_confidence == "high"
    assert hn.public_metadata_only is True
    assert hn.contact_allowed is False

    se = extract_requester_attribution(
        raw(
            "Can someone help integrate WeChat Pay for Shopify?",
            source="stackexchange",
            source_type="qa",
            url="https://stackoverflow.com/q/1",
            author="dev",
            metadata={"question_id": 1, "owner": {"display_name": "Dev User", "link": "https://stackoverflow.com/users/7/dev", "user_id": 7}},
        )
    )
    assert se.requester_display_name == "Dev User"
    assert se.requester_profile_url.endswith("/7/dev")
    assert se.attribution_confidence == "high"

    gdelt = extract_requester_attribution(raw("Need freight forwarder from China to US", source="gdelt", source_type="news", author="Reporter"))
    assert gdelt.requester_display_name == "unknown"
    assert gdelt.attribution_confidence == "unknown"

    unknown = extract_requester_attribution(raw("Need freight forwarder from China to US", source="unknown", author=""))
    assert unknown.requester_display_name == "unknown"
    assert unknown.requester_profile_url == ""


def test_public_contact_in_excerpt_is_redacted():
    lead = build_quick_service_lead(raw("I need a 1688 buying agent", "Email me at public@example.com or +1 555 123 4567"))
    assert lead is not None
    assert "public@example.com" not in lead.evidence_excerpt
    assert "555 123" not in lead.evidence_excerpt
    assert "redacted-public-email" in lead.evidence_excerpt


def test_report_and_json_expose_both_tracks(tmp_path):
    lead = build_quick_service_lead(raw("I need a 1688 buying agent"))
    md = tmp_path / "report.md"
    js = tmp_path / "summary.json"
    generate_markdown_report([], md, quick_service_leads=[lead.model_dump()])
    text = md.read_text(encoding="utf-8")
    assert "## Quick Service Leads" in text
    assert "## Product Opportunities" in text
    assert "No product opportunities found today." in text
    assert "## Requester Attribution Notes" in text
    assert "## Compliance Notes" in text

    generate_json_summary([], js, quick_service_leads=[lead.model_dump()], timing_diagnostics={"stage_statuses": {}})
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert payload["quick_service_lead_summary"]["total"] == 1
    assert payload["product_opportunity_summary"]["total"] == 0
    assert payload["requester_attribution_summary"]["with_public_requester"] == 1
    assert "timing_diagnostics" in payload


def test_pipeline_quick_leads_survive_when_product_opportunities_zero(tmp_path):
    raw_items_path = tmp_path / "raw_items.jsonl"
    report_path = tmp_path / "report.md"
    json_path = tmp_path / "summary.json"
    item = raw("I need help buy from Taobao", "Can someone help purchase order from Taobao", url="https://news.ycombinator.com/item?id=99")
    raw_items_path.write_text(json.dumps(item.model_dump()) + "\n", encoding="utf-8")
    run_fixture_pipeline(raw_items_path=raw_items_path, markdown_report_path=report_path, json_summary_path=json_path)
    text = report_path.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert "I need help buy from Taobao" in text
    assert payload["quick_service_lead_summary"]["total"] == 1
    assert payload["product_opportunity_summary"]["total"] == 0


def test_phase7_fix_01_rejects_article_blog_provider_false_positives():
    false_positives = [
        ("Inside The Fine Art Factories of Yiwu, China", "A factory tour and photo story about Yiwu fine art factories."),
        ("Article about Yiwu factories", "Blog post about China manufacturer workflow and export services."),
        ("This article talks about Dafen but not Yiwu", "I thought I would fill in history of the factories."),
        ("Guide to sourcing from China", "How to inspect suppliers in China and choose a China sourcing agent."),
        ("We offer China sourcing service", "Our company helps overseas sellers import from China."),
        ("Factory tour documentary", "Photo story inside the factories in Shenzhen."),
        ("News about WeChat Pay and China payment", "Report on payment integration adoption in China."),
        ("Alibaba supplier verification case study", "Posted by a public HN author, but it is an essay without a service request."),
        ("Show HN: JinbuPal – Learning Chinese doesn't have to be difficult", "I built a product for learning Chinese with lessons and flashcards."),
        ("Product launch: China sourcing dashboard", "We built software for supplier verification and freight forwarding teams."),
        ("Show HN: 1688 sourcing helper", "I made a tool for buyers; it can inspect suppliers and coordinate shipping."),
    ]
    for idx, (title, content) in enumerate(false_positives):
        item = raw(title, content, author="public_author", url=f"https://news.ycombinator.com/item?id=article-{idx}")
        classification = classify_demand(item)
        assert classification.track != "quick_service_lead", title
        assert build_quick_service_lead(item) is None
        if title == "Inside The Fine Art Factories of Yiwu, China":
            assert any(reason in classification.classification_reasons for reason in {"article_without_service_request", "no_explicit_service_request"})


def test_phase7_fix_01_preserves_true_quick_service_positives():
    positives = [
        "I need a 1688 buying agent",
        "Looking for someone in China to inspect supplier before shipment",
        "Need freight forwarder from China to US",
        "Can someone help integrate WeChat Pay for Shopify",
        "Need Chinese localization help",
        "Need supplier verification in Shenzhen",
        "Does anyone know a China customs clearance agent",
        "Where can I find a reliable Alibaba inspection service?",
        "Our company needs help with Alipay integration for overseas ecommerce",
        "Trying to buy from Taobao but need someone to consolidate and ship",
        "Show HN discussion: I need a freight forwarder from China to US",
    ]
    for idx, text in enumerate(positives):
        classification = classify_demand(raw(text, url=f"https://news.ycombinator.com/item?id=positive-{idx}"))
        assert classification.track == "quick_service_lead", text
        assert "source_primary_requester_signal" in classification.classification_reasons


def test_phase7_fix_01_metadata_and_news_boundaries_do_not_qualify():
    metadata_only = raw(
        "Inside The Fine Art Factories of Yiwu, China",
        "Factory workflow terms: supplier verification, inspection, freight forwarder.",
        author="hn_user",
        metadata={"objectID": "999", "query_category": "quick_service_lead"},
    )
    metadata_only.query_category = "quick_service_lead"
    metadata_only.source_profile = "direct_request"
    classification = classify_demand(metadata_only)
    assert classification.track != "quick_service_lead"

    china_workflow_only = classify_demand(raw("Alibaba supplier verification in Shenzhen"))
    deliverable_only = classify_demand(raw("Inspection support and shipping service"))
    metadata_comment_only = classify_demand(
        raw(
            "China freight discussion",
            "General China logistics article with freight forwarder terms.",
            metadata={"objectID": "comment-only", "comment_text": "I need a freight forwarder"},
        )
    )
    primary_text_request = classify_demand(raw("China freight discussion", "I need a freight forwarder from China to US"))
    gdelt_news = classify_demand(raw("Need freight forwarder from China to US", source="gdelt", source_type="news", author="Reporter"))
    assert china_workflow_only.track != "quick_service_lead"
    assert deliverable_only.track != "quick_service_lead"
    assert metadata_comment_only.track != "quick_service_lead"
    assert primary_text_request.track == "quick_service_lead"
    assert gdelt_news.track != "quick_service_lead"


def test_phase7_fix_01_summary_rejection_counts_and_zero_leads_report(tmp_path):
    items = [
        raw("Inside The Fine Art Factories of Yiwu, China", "Factory tour inside the factories in Yiwu."),
        raw("Alibaba supplier verification in Shenzhen"),
        raw("We offer China sourcing service", "We provide China sourcing services."),
    ]
    leads, rejected = classify_quick_service_leads(items)
    assert leads == []
    md = tmp_path / "report.md"
    js = tmp_path / "summary.json"
    generate_markdown_report([], md, quick_service_leads=leads, blocked_quick_service_items=rejected, timing_diagnostics={"stage_statuses": {}})
    text = md.read_text(encoding="utf-8")
    assert "No quick service leads found today." in text
    assert "quick_service_rejected_article_count" in text
    generate_json_summary([], js, quick_service_leads=leads, blocked_quick_service_items=rejected, timing_diagnostics={"stage_statuses": {}})
    payload = json.loads(js.read_text(encoding="utf-8"))
    summary = payload["quick_service_lead_summary"]
    assert summary["accepted_count"] == 0
    assert summary["candidate_count"] == len(rejected)
    assert summary["rejected_article_like_count"] >= 1
    assert summary["rejected_no_explicit_request_count"] >= 1
    assert summary["rejected_provider_side_count"] >= 1
    assert "timing_diagnostics" in payload


def test_phase7_fix_02_rejects_product_launch_and_maker_self_promotion():
    false_positives = [
        ("Show HN: JinbuPal – Learning Chinese doesn't have to be difficult", "My co-founder and I built a Chinese language learning web app."),
        ("Show HN: I built a Chinese language learning app", "I built a new app for Chinese learners."),
        ("My co-founder and I built a Chinese learning web app", "Announcing our product for Mandarin study."),
        ("We launched a tool for WeChat Pay integration", "SaaS launch for payment integration teams."),
        ("Our company provides China sourcing services", "We provide supplier verification and freight forwarding."),
        ("We help overseas sellers import from China", "Our service handles China sourcing workflows."),
        ("Guide to choosing a China sourcing agent", "Article about choosing a China sourcing agent."),
        ("How to source products from China", "How to source products from China and inspect suppliers."),
    ]
    for idx, (title, content) in enumerate(false_positives):
        item = raw(title, content, url=f"https://news.ycombinator.com/item?id=fix02-false-{idx}")
        classification = classify_demand(item)
        assert classification.track != "quick_service_lead", title
        assert build_quick_service_lead(item) is None
        assert any(
            reason in classification.classification_reasons
            for reason in {
                "product_launch_without_customer_request",
                "provider_side_without_customer_request",
                "article_without_service_request",
                "no_explicit_service_request",
            }
        ), title


def test_phase7_fix_02_preserves_explicit_customer_requests_and_hn_boundaries():
    positives = [
        "I need a 1688 buying agent",
        "Looking for someone in China to inspect supplier before shipment",
        "Need freight forwarder from China to US",
        "Can someone help integrate WeChat Pay for Shopify?",
        "Where can I find a China customs clearance agent?",
        "Trying to buy from Taobao but need someone to consolidate and ship",
        "Show HN: I need help finding a China sourcing agent",
    ]
    for idx, text in enumerate(positives):
        classification = classify_demand(raw(text, url=f"https://news.ycombinator.com/item?id=fix02-true-{idx}"))
        assert classification.track == "quick_service_lead", text
        assert "source_primary_requester_signal" in classification.classification_reasons

    boundaries = [
        raw("Show HN: China sourcing helper"),
        raw("Launch HN: China payment integration app"),
        raw("Ask HN: China sourcing agent", author="known_hn_author"),
        raw("We built China sourcing software"),
        raw("Product launch for China freight forwarder matching"),
        raw("Product launch: our company provides China sourcing services"),
    ]
    for item in boundaries:
        classification = classify_demand(item)
        assert classification.track != "quick_service_lead", item.title
        assert build_quick_service_lead(item) is None


def test_phase7_fix_02_summary_counts_product_launch_rejections(tmp_path):
    items = [
        raw("Show HN: JinbuPal – Learning Chinese doesn't have to be difficult", "My co-founder and I built a Chinese language learning web app."),
        raw("We launched a tool for WeChat Pay integration", "Introducing our product launch."),
        raw("Our company provides China sourcing services", "We provide China sourcing services."),
    ]
    leads, rejected = classify_quick_service_leads(items)
    assert leads == []
    md = tmp_path / "report.md"
    js = tmp_path / "summary.json"
    generate_markdown_report([], md, quick_service_leads=leads, blocked_quick_service_items=rejected, timing_diagnostics={"stage_statuses": {}})
    text = md.read_text(encoding="utf-8")
    assert "quick_service_rejected_product_launch_count" in text
    generate_json_summary([], js, quick_service_leads=leads, blocked_quick_service_items=rejected, timing_diagnostics={"stage_statuses": {}})
    summary = json.loads(js.read_text(encoding="utf-8"))["quick_service_lead_summary"]
    assert summary["rejected_product_launch_count"] >= 2
    assert summary["quick_service_rejected_product_launch_count"] >= 2
    assert summary["rejected_provider_side_count"] >= 1

def test_phase7_fix_03_jinbupal_rejected_in_full_report_json_path(tmp_path):
    items = [
        raw(
            "Show HN: JinbuPal – Learning Chinese doesn't have to be difficult",
            "My co-founder and I built a Chinese language learning web app that helps you quickly master the most common Chinese characters...",
            url="https://news.ycombinator.com/item?id=jinbupal-regression",
        )
    ]
    leads, rejected = classify_quick_service_leads(items)
    assert leads == []
    md = tmp_path / "report.md"
    js = tmp_path / "summary.json"
    generate_markdown_report([], md, quick_service_leads=leads, blocked_quick_service_items=rejected, timing_diagnostics={"stage_statuses": {}})
    generate_json_summary([], js, quick_service_leads=leads, blocked_quick_service_items=rejected, timing_diagnostics={"stage_statuses": {}})
    markdown = md.read_text(encoding="utf-8")
    payload = json.loads(js.read_text(encoding="utf-8"))
    summary = payload["quick_service_lead_summary"]
    lead_titles = [row["title"] for row in payload["quick_service_leads"]]
    assert "Show HN: JinbuPal – Learning Chinese doesn't have to be difficult" not in lead_titles
    assert "Show HN: JinbuPal – Learning Chinese doesn't have to be difficult" not in markdown.split("## Product Opportunities", 1)[0].split("## Blocked Quick Service Items", 1)[0]
    assert summary["accepted_count"] == 0
    assert summary["quick_service_rejected_product_launch_count"] == 1
    assert payload["quick_service_leads"] == []
    blocked = payload["blocked_quick_service_items"]
    assert blocked[0]["title"] == "Show HN: JinbuPal – Learning Chinese doesn't have to be difficult"
    assert "product_launch_without_customer_request" in blocked[0]["classification_reasons"]
    assert "provider_side_without_customer_request" in blocked[0]["classification_reasons"]
    assert "maker_self_promotion_without_customer_request" in blocked[0]["classification_reasons"]
    assert "demand_side_service_request_signal" not in blocked[0]["classification_reasons"]
    assert "No quick service leads found today." in markdown
