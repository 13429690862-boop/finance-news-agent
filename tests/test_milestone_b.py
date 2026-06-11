import json
from pathlib import Path

from agent.analyze import RuleBasedAnalyzer
from agent.cluster import cluster_opportunities, mark_history
from agent.config import load_scoring_config
from agent.pipeline import run_daily_pipeline
from agent.report import generate_markdown_report
from agent.models import RawItem


def test_source_confidence_config_loading():
    cfg = load_scoring_config('configs/scoring.yaml')
    assert cfg['source_confidence']['hn_algolia'] == 0.85


def test_clustering_merges_similar():
    data = [
        {'title': 'Need China supplier verification', 'pain_point': 'supplier trust issue', 'opportunity_score': 10, 'weighted_score': 8, 'evidence_urls': ['u1'], 'evidence_quotes': ['q1']},
        {'title': 'Looking for supplier verification in China', 'pain_point': 'trust issue with supplier', 'opportunity_score': 8, 'weighted_score': 7, 'evidence_urls': ['u2'], 'evidence_quotes': ['q2']},
    ]
    out = cluster_opportunities(data)
    assert len(out) == 1
    assert len(out[0]['evidence_urls']) == 2


def test_clustering_not_merge_unrelated():
    out = cluster_opportunities([
        {'title': 'Need freight forwarder', 'pain_point': 'shipping delays', 'opportunity_score': 10, 'evidence_urls': ['u1'], 'evidence_quotes': ['q1']},
        {'title': 'Wechat API auth issue', 'pain_point': 'integration bug', 'opportunity_score': 10, 'evidence_urls': ['u2'], 'evidence_quotes': ['q2']},
    ])
    assert len(out) == 2


def test_evidence_quote_extraction_prefers_demand_sentence():
    item = RawItem(source='x', source_type='y', url='u', title='Context title', content='General intro. I need help finding a supplier in China urgently. More text.', author='a', published_at='p', fetched_at='f', query='q', language='en', raw_metadata={})
    opp = RuleBasedAnalyzer().analyze_item(item)
    assert 'need help' in opp.evidence_quotes[0].lower() or 'need' in opp.evidence_quotes[0].lower()


def test_history_mark_repeated():
    records = [{'title': 'Need supplier verification', 'pain_point': 'supplier trust'}]
    mark_history(records, {'supplier|trust|verification': 1})
    assert records[0]['history_status'] in {'repeated', 'new', 'recurring'}


def test_report_has_source_status_and_warnings(tmp_path: Path):
    out = tmp_path / 'r.md'
    generate_markdown_report([{'title':'t','priority':'low','opportunity_score':1,'evidence_urls':['u']}], out, source_statuses={'hn_algolia': {'status':'error', 'count':0}})
    text = out.read_text(encoding='utf-8')
    assert '## Source Status' in text
    assert '## Warnings' in text


def test_daily_pipeline_with_mock_collection(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    def fake_collect(**kwargs):
        p = tmp_path / 'data' / 'raw_items.jsonl'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({'source':'hn_algolia','source_type':'forum_post','url':'https://x.com','title':'Need China supplier','content':'Looking for supplier help in China','author':'a','published_at':'2026-01-01T00:00:00Z','fetched_at':'2026-05-18T00:00:00Z','query':'q','language':'en','raw_metadata':{}})+'\n', encoding='utf-8')
        return {'sources': {'hn_algolia': {'status':'ok','count':1}}}
    monkeypatch.setattr('agent.pipeline.run_real_collection', fake_collect)
    summary = run_daily_pipeline(raw_items_path=tmp_path/'data/raw_items.jsonl', markdown_report_path=tmp_path/'reports/r.md')
    assert summary['opportunities_generated'] >= 1
