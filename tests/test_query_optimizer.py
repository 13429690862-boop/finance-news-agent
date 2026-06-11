import json
from pathlib import Path

from agent.query_optimizer import FORBIDDEN_BROAD_TERMS, generate_query_adjustment_proposals
from agent.report import generate_json_summary, generate_markdown_report


def _diag():
    return {
        "source_recommendations": [
            {"scope": "source", "name": "stackexchange", "problem_type": "source_zero_return"},
            {"scope": "source", "name": "gdelt", "problem_type": "source_all_rejected"},
            {"scope": "source", "name": "hn_algolia", "problem_type": "high_qualified_low_final"},
        ],
        "category_recommendations": [
            {"scope": "category", "name": "china_sourcing_agents", "problem_type": "high_collected_low_qualified"},
            {"scope": "category", "name": "software_api_workflows", "problem_type": "category_no_recall"},
            {"scope": "category", "name": "china_payment_api", "problem_type": "high_qualified_low_final"},
            {"scope": "category", "name": "china_localization", "problem_type": "category_too_broad"},
        ],
    }


def test_proposal_mapping_rules():
    proposals = generate_query_adjustment_proposals(_diag(), {"enabled": True})
    assert any(p["name"] == "stackexchange" and p["proposed_action"] == "review_source_profile" for p in proposals)
    assert any(p["name"] == "gdelt" and p["proposed_action"] == "move_to_supporting" for p in proposals)
    assert any(p["problem_type"] == "high_collected_low_qualified" and p["proposed_action"] == "narrow" for p in proposals)
    assert any(p["name"] == "china_payment_api" and "workflow" in p["rationale"].lower() for p in proposals)
    assert any(p["name"] == "software_api_workflows" and p["proposed_action"] == "expand" for p in proposals)
    assert any(p["name"] == "china_localization" and p["proposed_action"] == "narrow" for p in proposals)


def test_additions_are_safe():
    proposals = generate_query_adjustment_proposals(_diag(), {"enabled": True})
    additions = [q.lower() for p in proposals for q in p.get("proposed_query_additions", [])]
    assert additions
    assert not any(term in q for term in FORBIDDEN_BROAD_TERMS for q in additions)


def test_dry_run_no_query_config_mutation():
    before = Path("configs/queries.yaml").read_text(encoding="utf-8")
    _ = generate_query_adjustment_proposals(_diag(), {"enabled": True, "dry_run": True, "apply_changes": False, "allow_production_config_mutation": False})
    after = Path("configs/queries.yaml").read_text(encoding="utf-8")
    assert before == after


def test_report_and_json_sections_include_proposals(tmp_path):
    proposals = generate_query_adjustment_proposals(_diag(), {"enabled": True})
    md = tmp_path / "r.md"
    js = tmp_path / "s.json"
    generate_markdown_report([], md, telemetry={"source_telemetry": {}, "category_telemetry": {}}, recall_diagnostics=_diag(), query_adjustment_proposals=proposals)
    text = md.read_text(encoding="utf-8")
    assert "## Query/Profile Adjustment Proposals" in text
    generate_json_summary([], js, query_adjustment_proposals=proposals, recall_diagnostics=_diag())
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert "query_adjustment_proposals" in payload


def _proposal_for(proposals, name):
    return [p for p in proposals if p["scope"] == "category" and p["name"] == name]


def test_category_specific_templates_and_mismatch_protection():
    diag = {
        "source_recommendations": [],
        "category_recommendations": [
            {"scope": "category", "name": "china_localization", "problem_type": "category_no_recall"},
            {"scope": "category", "name": "software_api_workflows", "problem_type": "category_no_recall"},
            {"scope": "category", "name": "china_payment_api", "problem_type": "category_no_recall"},
            {"scope": "category", "name": "china_sourcing_agents", "problem_type": "category_no_recall"},
            {"scope": "category", "name": "cross_border_logistics", "problem_type": "category_no_recall"},
        ],
    }
    proposals = generate_query_adjustment_proposals(diag, {"enabled": True, "max_additions_per_category": 6})

    localization = " ".join(q.lower() for p in _proposal_for(proposals, "china_localization") for q in p["proposed_query_additions"])
    assert "1688" not in localization and "sourcing" not in localization and "freight" not in localization

    api = " ".join(q.lower() for p in _proposal_for(proposals, "software_api_workflows") for q in p["proposed_query_additions"])
    assert "freight" not in api and "supplier" not in api

    payment = " ".join(q.lower() for p in _proposal_for(proposals, "china_payment_api") for q in p["proposed_query_additions"])
    assert "pay" in payment or "payment" in payment or "gateway" in payment

    sourcing = " ".join(q.lower() for p in _proposal_for(proposals, "china_sourcing_agents") for q in p["proposed_query_additions"])
    assert any(term in sourcing for term in ["sourcing", "supplier", "qc", "manufacturer"])

    logistics = " ".join(q.lower() for p in _proposal_for(proposals, "cross_border_logistics") for q in p["proposed_query_additions"])
    assert any(term in logistics for term in ["shipping", "freight", "customs", "forwarding"])

def test_high_qualified_low_final_uses_category_specific_safe_templates():
    diag = {
        "source_recommendations": [],
        "category_recommendations": [
            {"scope": "category", "name": "china_payment_api", "problem_type": "high_qualified_low_final"},
            {"scope": "category", "name": "china_sourcing_agents", "problem_type": "high_qualified_low_final"},
            {"scope": "category", "name": "cross_border_logistics", "problem_type": "high_qualified_low_final"},
            {"scope": "category", "name": "software_api_workflows", "problem_type": "high_qualified_low_final"},
            {"scope": "category", "name": "china_localization", "problem_type": "high_qualified_low_final"},
        ],
    }
    proposals = generate_query_adjustment_proposals(diag, {"enabled": True, "max_additions_per_category": 6})

    payment = " ".join(q.lower() for p in _proposal_for(proposals, "china_payment_api") for q in p["proposed_query_additions"])
    assert not any(term in payment for term in ["supplier onboarding", "sourcing", "freight", "logistics sop", "qc", "factory", "manufacturer"])
    assert any(term in payment for term in ["pay", "payment", "gateway", "merchant account"])

    sourcing = " ".join(q.lower() for p in _proposal_for(proposals, "china_sourcing_agents") for q in p["proposed_query_additions"])
    assert any(term in sourcing for term in ["sourcing", "supplier", "qc", "manufacturer"])

    logistics = " ".join(q.lower() for p in _proposal_for(proposals, "cross_border_logistics") for q in p["proposed_query_additions"])
    assert any(term in logistics for term in ["shipping", "freight", "customs", "forwarder", "forwarding"])

    api = " ".join(q.lower() for p in _proposal_for(proposals, "software_api_workflows") for q in p["proposed_query_additions"])
    assert all(term not in api for term in ["supplier", "qc", "freight", "manufacturer"])
    assert any(term in api for term in ["api", "integration", "program"])

    localization = " ".join(q.lower() for p in _proposal_for(proposals, "china_localization") for q in p["proposed_query_additions"])
    assert all(term not in localization for term in ["supplier", "qc", "freight", "manufacturer", "api access"])
    assert any(term in localization for term in ["localize", "localization", "compliance", "translate", "support"])


def test_all_category_proposal_paths_use_category_safe_templates():
    diag = {
        "source_recommendations": [],
        "category_recommendations": [
            {"scope": "category", "name": "china_payment_api", "problem_type": "category_too_broad"},
            {"scope": "category", "name": "china_payment_api", "problem_type": "category_no_recall"},
            {"scope": "category", "name": "china_payment_api", "problem_type": "high_qualified_low_final"},
        ],
    }
    proposals = generate_query_adjustment_proposals(diag, {"enabled": True, "max_additions_per_category": 6})
    expected = {
        "wechat pay api integration overseas",
        "alipay payment gateway for shopify",
        "need help integrating wechat pay",
        "china payment gateway for foreign company",
        "wechat pay merchant account overseas",
        "alibaba payment integration for supplier orders",
    }

    for p in proposals:
        if p["scope"] == "category" and p["name"] == "china_payment_api":
            got = {q.lower() for q in p["proposed_query_additions"]}
            assert got.issubset(expected)
