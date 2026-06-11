# china-demand-agent-dev

海外对中国相关需求发现 agent 的开发环境。Codex 仅负责代码开发、测试和维护；每日生产运行由 GitHub Actions 或 Cloud Run 执行 in a later phase.

## Bootstrap and Phase 1C status

This repository contains a minimal, local-only Python bootstrap plus the Phase 1A source-ingestion contract, Phase 1B offline transformation layer, and Phase 1C offline quality improvements. It still does **not** implement network collectors or production integrations.

Included in the Phase 0 bootstrap:

- Opportunity scoring and priority classification helpers.
- In-memory item deduplication by exact URL and normalized title.
- Simple report generation fixtures.
- A `test-fixture` CLI mode that uses fake opportunities only.
- Pytest coverage for scoring, deduplication, and report generation.

Added in Phase 1A:

- `RawItem` and `DemandOpportunity` data contracts with validation for bounded factor scores, priorities, and evidence URLs.
- Base source collector contracts for future ingestion adapters.
- A deterministic offline `MockCollector` backed by JSON fixtures.
- Query loading and flattening from `configs/queries.yaml`.
- A `collect-fixture` CLI mode that loads configured queries and writes fixture raw items to JSONL for local validation.

Added in Phase 1B:

- A deterministic offline `RuleBasedAnalyzer` that converts fixture `RawItem` records into `DemandOpportunity` candidates.
- Keyword-based demand detection and rule-based heuristics for China relevance, market intensity, implementation difficulty, and monetization clarity.
- Formula-based opportunity scoring with the existing priority classifier.
- A fixture analysis pipeline and `analyze-fixture` CLI mode that reads `data/raw_items.jsonl`, writes `reports/fixture-opportunities-report.md`, and prints raw item and opportunity counts.

Added in Phase 1C:

- An expanded offline query taxonomy in `configs/queries.yaml` with 12 categories and at least 80 English queries.
- A deterministic scoring configuration file in `configs/scoring.yaml` for demand intent, China relevance, market intensity, implementation difficulty, monetization clarity, customer-type, risk-note, and solution rules.
- `RuleBasedAnalyzer(scoring_config: dict | None = None)`, preserving safe built-in defaults while allowing the pipeline and tests to load auditable scoring rules from config.
- A polished Markdown report format with generated timestamp, executive summary, priority counts, sorted top-opportunity table, score breakdown, customer type, pain point, solution, monetization model, evidence URLs, evidence quotes, risk notes, and next validation step.
- Optional JSON summary report support for local or test use. Generated JSON summaries are ignored by Git.

The bootstrap through Phase 1C requires no real API keys and does not call external APIs in tests, fixture collection, or fixture analysis. Real network collectors and integrations are intentionally out of scope.

## Expanded query taxonomy

`configs/queries.yaml` groups English demand-discovery searches into these categories:

- `sourcing`
- `suppliers`
- `1688_taobao`
- `logistics`
- `ecommerce`
- `china_market_entry`
- `chinese_localization`
- `chinese_platforms`
- `manufacturing`
- `software_api`
- `quality_control`
- `negative_complaints`

The taxonomy covers themes such as looking for Chinese manufacturers, Alibaba alternatives, 1688/Taobao agent issues, China sourcing help, freight forwarders, Chinese payment gateways for foreigners, WeChat API problems, selling to Chinese customers, Chinese localization, supplier ghosting, quality-control problems, importing from China, factory verification, private label suppliers, OEM/ODM manufacturers, and supplier communication problems.

## Scoring config

`configs/scoring.yaml` moves deterministic analyzer keywords and rules into config:

- `demand_intent_keywords`
- `china_relevance_keywords`
- `market_intensity_high_keywords`
- `market_intensity_medium_keywords`
- `implementation_difficulty_high_keywords`
- `implementation_difficulty_medium_keywords`
- `monetization_clarity_high_keywords`
- `monetization_clarity_medium_keywords`
- `customer_type_rules`
- `risk_note_rules`
- `solution_rules`

`agent.config.load_scoring_config()` validates required sections and reports clear errors for missing or invalid scoring config. If no scoring config is supplied to `RuleBasedAnalyzer`, the analyzer uses built-in defaults compatible with Phase 1B behavior.

## Report format

The Markdown fixture opportunity report includes:

- Report title and generated date/time.
- Executive summary.
- Total opportunity count plus high, medium, and low priority counts.
- A top-opportunities table sorted by `opportunity_score` descending.
- Detailed sections for each opportunity with title, priority, score breakdown, customer type, pain point, possible solution, monetization model, evidence URLs, evidence quotes, risk notes, and next validation step.

Generated report files are runtime artifacts and are ignored by Git:

- `reports/*.md`
- `reports/*.json`
- `data/*.jsonl`

## How to run

Compile the Python modules and tests:

```bash
python -m compileall agent tests
```

Run the test suite:

```bash
pytest -q
```

Generate the local raw-item fixture output:

```bash
python -m agent.main --mode collect-fixture
```

The collection fixture command prints the query count, item count, and output path. It writes:

```text
data/raw_items.jsonl
```

Analyze the collected raw fixture items:

```bash
python -m agent.main --mode analyze-fixture
```

The analysis fixture command loads `configs/scoring.yaml` when present, prints the raw item count, opportunity count, and report path, and writes:

```text
reports/fixture-opportunities-report.md
```

Optionally write a JSON summary during fixture analysis:

```bash
python -m agent.main --mode analyze-fixture --json-summary
```

Generate the local test-fixture report:

```bash
python -m agent.main --mode test-fixture
```

The report fixture command writes:

```text
reports/test-fixture-demand-report.md
```

Generated JSONL data files, Markdown report files, and JSON report files are ignored by Git. `data/.gitkeep` and `reports/.gitkeep` keep those directories present in fresh checkouts.

## Phase boundaries

Phase 1C remains intentionally small and auditable:

- Uses only offline fixtures.
- Does not add real network collectors.
- Does not call external APIs.
- Does not require API keys.
- Does not add OpenAI, Tavily, Reddit, Notion, GitHub Actions, or Cloud Run integration.
- Preserves the existing `collect-fixture`, `analyze-fixture`, and `test-fixture` behavior.

## Next recommended phase

After Phase 1C is stable, the next phase can improve grouping/deduplication across multiple `RawItem` signals or add manually reviewed validation workflows before enabling any real networked collection or LLM-based enrichment.

## Phase 2A status: HN Algolia real collector

Phase 2A adds the first production-safe real collector: **Hacker News Algolia** (`hn_algolia`) behind the existing `SourceCollector` interface.

What this collector does:

- Calls the HN Algolia search endpoint with configured queries.
- Requires **no API key**.
- Applies timeout and user-agent.
- Gracefully handles malformed responses and HTTP failures (returns partial/empty results instead of crashing).
- Skips empty/unusable hits.
- De-duplicates items by URL/title.
- Maps HN fields into `RawItem` with:
  - `source="hn_algolia"`
  - `source_type="discussion"`
  - URL fallback to HN item URL when `story_url` is missing.

Source config (`configs/sources.yaml`):

- `hn_algolia.enabled: true`
- `hn_algolia.max_items: 20`
- `hn_algolia.timeout_seconds: 15`

New CLI mode:

```bash
python -m agent.main --mode collect-hn
```

This mode:

- loads queries from `configs/queries.yaml`
- runs `HNAlgoliaCollector`
- writes `data/raw_items.jsonl`
- prints source name, query count, raw item count, and output path

Phase 2A scope boundaries (still deferred):

- HN Algolia is the **only** real collector in this phase.
- OpenAI, Tavily, Reddit, Notion, GitHub Actions, Cloud Run, GDELT, and Stack Exchange integrations are still deferred.
- Test coverage uses mocked collector HTTP behavior and does **not** require live external network access.


## Phase 2B status: GDELT real collector

Phase 2B adds **GDELT** as the next production-safe real collector behind the existing `SourceCollector` interface.

What this collector does:

- Calls the public GDELT Doc API (`mode=ArtList`) with configured queries.
- Requires **no API key**.
- Applies timeout and user-agent via `httpx` when available.
- Gracefully handles malformed payloads, HTTP errors, and exceptions (returns partial/empty results instead of crashing).
- Skips empty/unusable records.
- De-duplicates by URL/title.
- Maps GDELT records into `RawItem` with:
  - `source="gdelt"`
  - `source_type="news"`
  - `content` composed from title + snippet/context fallback.

Source config (`configs/sources.yaml`):

- `gdelt.enabled: true`
- `gdelt.max_items: 20`
- `gdelt.timeout_seconds: 15`

New CLI mode:

```bash
python -m agent.main --mode collect-gdelt
```

This mode:

- loads queries from `configs/queries.yaml`
- loads source settings from `configs/sources.yaml`
- runs `GDELTCollector`
- writes `data/raw_items.jsonl`
- prints source name, query count, raw item count, and output path

Phase 2B boundaries:

- Real collectors currently implemented: **HN Algolia** and **GDELT** only.
- Test coverage for collector behavior uses mocked network responses and does **not** call live external services.
- OpenAI, Tavily, Reddit, Notion, Stack Exchange, GitHub Actions, and Cloud Run integrations remain deferred.

## Phase 2C status: Stack Exchange real collector

Phase 2C adds **Stack Exchange** as the next production-safe real collector behind the existing `SourceCollector` interface.

What this collector does:

- Calls the public Stack Exchange search API (`/2.3/search`) with configured queries.
- Defaults to `site=stackoverflow`.
- Requires **no API key**.
- Applies timeout and user-agent via `httpx` when available.
- Gracefully handles malformed payloads, HTTP errors, and exceptions (returns partial/empty results instead of crashing).
- Skips empty/unusable records.
- De-duplicates by URL/title.
- Maps Stack Exchange records into `RawItem` with:
  - `source="stackexchange"`
  - `source_type="qa"`
  - `published_at` from `creation_date` when available
  - compact metadata with score, answer count, tags, site, and question id.

Source config (`configs/sources.yaml`):

- `stackexchange.enabled: true`
- `stackexchange.site: "stackoverflow"`
- `stackexchange.max_items: 20`
- `stackexchange.timeout_seconds: 15`

New CLI mode:

```bash
python -m agent.main --mode collect-stackexchange
```

This mode:

- loads queries from `configs/queries.yaml`
- loads source settings from `configs/sources.yaml`
- runs `StackExchangeCollector`
- writes `data/raw_items.jsonl`
- prints source name, query count, raw item count, and output path

Phase 2C boundaries:

- Real collectors currently implemented: **HN Algolia**, **GDELT**, and **Stack Exchange** only.
- Collector tests use mocked network behavior and do **not** call real external services.
- OpenAI, Tavily, Reddit, Notion, GitHub Actions, and Cloud Run integrations remain deferred.

## Milestone A: Automated real-collection Markdown MVP

Status: implemented.

Commands:
- `python -m agent.main --mode collect-real`
- `python -m agent.main --mode daily`
- optional summary output: add `--json-summary`

Daily automation:
- GitHub Actions workflow: `.github/workflows/daily.yml`
- Schedule: daily at 09:00 Beijing time (01:00 UTC)
- Also supports `workflow_dispatch`
- Artifacts: always uploads `reports/`; uploads `data/raw_items.jsonl` only when present

Current real sources:
- HN Algolia
- GDELT
- Stack Exchange

Deferred integrations:
- OpenAI
- Tavily
- Reddit
- Notion
- Feishu
- Cloud Run

Limitations:
- rule-based analysis only
- no LLM ranking yet
- public-source coverage only
- network availability may affect live runs

## Milestone B status (deterministic quality/ranking/trends)

- Added source confidence weighting (`weighted_score = opportunity_score * source_confidence`) via `configs/scoring.yaml` and pipeline enrichment.
- Added deterministic clustering (`agent/cluster.py`) using normalized token keys, merged evidence, and representative selection by weighted score.
- Added JSONL historical baseline (`data/opportunity_index.jsonl`) read/write for `new` / `repeated` / `recurring` statuses.
- Improved evidence quote extraction in rule-based analysis (demand-keyword sentence preference and length trimming).
- Improved report sections: executive summary, source status table, warnings, weighted score display, cluster/source/evidence counts, historical status, and next validation actions.
- Added deterministic quality flags: `weak_evidence`, `low_china_relevance`, `high_implementation_risk`, `single_source_only`, `possible_news_only`.

### Limitations

- No OpenAI/LLM calls.
- No API-key dependencies.
- Clustering and historical matching are token/rule based and may miss semantic similarity edge cases.

## Milestone C status: Optional OpenAIAnalyzer

Milestone C adds an **optional** OpenAIAnalyzer. Enable with `ANALYZER_MODE=openai` or `ANALYZER_MODE=auto`, plus `OPENAI_API_KEY` and optional `OPENAI_MODEL`.

Fallback behavior:
- If `OPENAI_API_KEY` is missing, the pipeline safely falls back to `RuleBasedAnalyzer`.
- Default operation and tests do not require API keys.
- GitHub Actions daily workflow continues to run with no secrets.
- Tests mock OpenAI behavior and never call the real OpenAI API.

Deferred integrations remain:
- Notion
- Feishu
- Tavily
- Reddit
- Cloud Run

## Milestone D: Demand Quality Gate

- Added deterministic quality gate before analysis to reduce false positives.
- Reports now include qualified/rejected raw-item counts, rejection reasons, and sample rejected items.
- GDELT is treated as news evidence and is filtered unless explicit commercial demand exists.
- Fewer opportunities is expected and zero qualified opportunities is a valid outcome.
- OpenAIAnalyzer remains optional and fallback-safe without OPENAI_API_KEY.

Validation commands:
- `python -m compileall agent tests`
- `pytest -q`
- `python -m agent.main --mode collect-real`
- `python -m agent.main --mode daily`

## Milestone E1 status: demand-oriented recall and source routing

Milestone E1 keeps Milestone D precision gates intact while improving recall quality at collection time.

- Query taxonomy in `configs/queries.yaml` is now demand-oriented and focused on real workflow phrasing (sourcing agent, supplier verification, freight forwarding, payment API integration, localization, market entry, and China API workflows).
- Source-specific query routing is supported via `source_profiles`:
  - `hn_algolia`: broad demand workflow mix.
  - `stackexchange`: payment/API/localization workflow emphasis.
  - `gdelt`: constrained sourcing/logistics/market-entry demand phrasing only.
- If a source profile is missing, the system safely falls back to flattened queries for backward compatibility.
- HN/GDELT/Stack Exchange now use different routed query sets in per-source CLI modes and `collect-real`.
- GDELT remains a supporting-news source and is not broadened to generic China news/politics/culture searching.
- Reports now include a deterministic **Recall Notes** section so zero final opportunities is treated as a valid "no qualified China workflow demand found" outcome, not a pipeline failure.
- No new secrets are required. `OPENAI_API_KEY` remains optional (only for optional analyzer fallback paths), and daily execution continues without it.
- No DeepSeek/LLM triage changes are introduced in E1; those remain future work.

## Milestone E2 (Source/Category Telemetry)

E2 adds deterministic recall diagnostics telemetry at source/category/query levels across stages: collected, deduped raw, quality gate input, qualified raw, analyzed candidates, and final qualified/rejected. Daily and JSON summary outputs now include telemetry blocks to support evidence-based query/source tuning without new integrations or secrets. OpenAI analyzer remains optional fallback-safe; strict quality/final filters remain unchanged.

## Milestone E3: Recall Optimization Loop

E3 adds deterministic recall diagnostics driven by telemetry (source and category dropoff) without weakening the quality gate or final opportunity filter.

- Recommendations classify bottlenecks such as `source_zero_return`, `source_all_rejected`, `high_qualified_low_final`, `category_no_recall`, and `category_too_broad`.
- The daily Markdown report now includes a **Recall Optimization Recommendations** table (top 10 by severity).
- `daily --json-summary` includes `recall_diagnostics` with:
  - `source_recommendations`
  - `category_recommendations`
  - `query_suggestions`

How to interpret actions:
- `narrow`: tighten to explicit demand/workflow language.
- `expand`: add alternative demand-oriented phrases when a category has zero recall.
- `pause`: pause low-signal/noisy query groups (future operational step).
- `review_source_profile`: revisit source/category routing (for example Stack Exchange zero return).
- `move_to_supporting`: keep source as supporting evidence, not primary discovery (for example GDELT/news-like feeds).

These recommendations do **not** auto-relax filters and do **not** auto-rewrite taxonomy globally; they guide next safe query/source adjustments.

DeepSeek/LLM triage remains deferred until source/query telemetry is stable and recall bottlenecks are better understood. E3 requires no new secrets or external integrations.

## Phase E5 status: Source Recall Expansion and StackExchange Repair

- StackExchange recall repair now supports explicit multi-site collection (`stackoverflow`, `webmasters`, `softwareengineering`, `magento`, `wordpress`, `salesforce`) with deterministic query adaptation for API/localization/payment workflows.
- Source roles are explicit: HN = discovery candidate source, GDELT = supporting/news context source, StackExchange = technical/API workflow source.
- Source Recall Diagnostics are now emitted in Markdown and JSON (`source_recall_diagnostics`) so zero-recall and supporting-only behavior are visible per source.
- No new secrets/integrations were added; `OPENAI_API_KEY` is still not required.
- DeepSeek and LLM triage remain deferred until raw recall improves.

## Production Phase 2 Safety
- AI triage is optional and disabled by default (`configs/ai_triage.yaml`).
- Delivery is optional and disabled by default (`configs/delivery.yaml`).
- No-secret daily runs stay safe: rule-based analysis + skipped delivery.
- Mock providers (`mock_coarse`, `mock_final`) and mocked SMTP tests are available for CI-safe validation.
- AI triage is advisory only and cannot bypass deterministic quality gate or final opportunity filter.
- Delivery sends only when explicitly enabled and fully configured with SMTP secrets.


## Production Phase 4 Controlled Dry Run

- Default runs remain no-secret-safe.
- Use `python -m agent.main --mode secrets-audit --profile no_secret_default` for CI-safe readiness.
- Use `--profile ai_provider_dry_run`, `delivery_test_recipient`, or `full_test_dry_run` for explicit checks.
- `ai-provider-check` is connectivity/schema-only and never qualifies opportunities.
- `delivery-check` in test mode sends only to `REPORT_TEST_RECIPIENT_EMAIL`.

## Phase 5: Scheduled Test-Recipient Daily Delivery (Safe Opt-In)

- Scheduled auto-send is **disabled by default**.
- To enable scheduled test-recipient delivery, set repository variable:
  - `SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT=true`
- To disable again, unset it or set any non-`true` value.
- Scheduled send path only targets `REPORT_TEST_RECIPIENT_EMAIL` and does not send to non-test recipients.
- `REPORT_RECIPIENT_EMAIL` is not used for scheduled test-recipient delivery unless it equals the test recipient.
- AI provider remains disabled unless explicitly requested via manual workflow dispatch inputs.

Required secrets for scheduled/manual test-recipient send:
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `REPORT_SENDER_EMAIL`
- `REPORT_TEST_RECIPIENT_EMAIL`

Generated artifacts:
- `reports/daily-demand-report.md`
- `reports/daily-demand-summary.json`
- `reports/daily-delivery-status.json` (sanitized send-attempt result)

Rollback:
1. Set `SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT` to `false` (or remove it).
2. Keep manual `send_report_to_test_recipient` workflow dispatch for controlled tests only.
3. Verify scheduled runs return to artifact-only behavior.

## Optional two-stage AI layer (DeepSeek + OpenAI Responses)

The optional AI layer is disabled by default and never weakens deterministic gates.

1. **DeepSeek coarse triage** defaults to raw provider model id `deepseek-v4-pro` with `reasoning_effort: max` and `context_window: default`, and runs only after the deterministic raw-item quality gate accepts an item. It may drop noisy already-qualified raw items, but it cannot qualify rejected raw records. Do not put Claude Code context aliases such as `[1m]` in `AI_COARSE_MODEL`; use `AI_COARSE_CONTEXT_WINDOW=1m` to record long-context operator intent.
2. **OpenAI Responses final scoring** runs only after the deterministic final opportunity sanity filter accepts an opportunity. It enriches reports and JSON with feasibility, urgency, confidence, risks, assumptions, and next-step analysis, but it is not a deterministic gatekeeper.
3. **True Codex SDK / local Codex agent integration is not implemented.** The final scoring adapter uses `OpenAI().responses.create(...)` with a Codex-style prompt, not the Codex CLI, local Codex SDK, or a Codex agent path. ChatGPT membership is not an API credential for scheduled runs.

Default provider check (no live request with default disabled config):

```bash
python -m agent.main --mode ai-provider-check
```

Controlled DeepSeek-only live dry-run (requires only `DEEPSEEK_API_KEY`; OpenAI final scoring stays disabled):

```bash
python -m agent.main --mode ai-provider-check --profile deepseek_coarse_dry_run --provider deepseek
```

See `docs/two_stage_ai_operator_guide.md` for the full operator flow and safe DeepSeek-only config state.

## Phase 6-FIX-02 operator configuration and audits

Phase 6-FIX-02 exposes safe operator-facing switches through YAML plus environment/GitHub Variables while preserving the deterministic quality gate and final opportunity filter as authoritative. It does **not** add a public web admin UI, does **not** print secret values, does **not** enable AI by default, and does **not** enable non-test-recipient delivery.

### Source and crawl interfaces

Edit `configs/sources.yaml` or set these GitHub Variables/environment variables for one run:

- `SOURCE_HN_ENABLED` -> `hn_algolia.enabled`
- `SOURCE_GDELT_ENABLED` -> `gdelt.enabled`
- `SOURCE_STACKEXCHANGE_ENABLED` -> `stackexchange.enabled`

Each configured source supports safe non-secret fields: `enabled`, `source_type`, `role`, `max_results`, `timeout_seconds`, and optional `include_categories`. StackExchange additionally supports `site` and `sites`. Query categories and source query profiles remain in `configs/queries.yaml` under `queries` and `source_profiles`.

Disabled sources are skipped cleanly, an empty enabled source set produces an empty daily report instead of crashing, unknown source names fail validation, and StackExchange `sites` must be a list of strings.

### AI interfaces

Safe AI settings live in `configs/ai_triage.yaml` and may be overridden with GitHub Variables/environment variables:

- Global: `AI_TRIAGE_ENABLED`, `AI_ALLOW_BYPASS_FINAL_FILTER` (must remain false), `AI_DEFAULT_PROFILE`
- DeepSeek coarse: `AI_COARSE_ENABLED`, `AI_COARSE_PROVIDER`, `AI_COARSE_MODEL`, `AI_COARSE_CONTEXT_WINDOW`, `AI_COARSE_ENABLE_1M_CONTEXT`, `AI_COARSE_BASE_URL`, `AI_COARSE_REASONING_EFFORT`, `AI_COARSE_TIMEOUT_SECONDS`, `AI_COARSE_BATCH_SIZE`, `AI_COARSE_SAMPLE_LIMIT`, `AI_COARSE_TEMPERATURE`, `AI_COARSE_MAX_OUTPUT_TOKENS`
- OpenAI final: `AI_FINAL_ENABLED`, `AI_FINAL_PROVIDER`, `AI_FINAL_MODEL`, `AI_FINAL_BASE_URL`, `AI_FINAL_TIMEOUT_SECONDS`, `AI_FINAL_SAMPLE_LIMIT`

Defaults keep AI disabled, DeepSeek coarse configured as `provider=deepseek`, raw daily-agent `model=deepseek-v4-pro`, `context_window=default`, `reasoning_effort=max`, and OpenAI Responses final scoring disabled. Allowed `reasoning_effort` values are `none`, `low`, `medium`, `high`, and `max`; allowed `AI_COARSE_CONTEXT_WINDOW` values are `default` and `1m`. `true_codex_sdk_supported=false` and `true_codex_sdk_enabled=false`; true Codex SDK/local agent integration is not implemented.

Claude Code / Anthropic-compatible tooling may use aliases such as `ANTHROPIC_MODEL=deepseek-v4-pro[1m]`, `ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro[1m]`, and `ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-pro[1m]`. The daily agent must instead use `AI_COARSE_MODEL=deepseek-v4-pro`, `AI_COARSE_CONTEXT_WINDOW=1m`, and `AI_COARSE_REASONING_EFFORT=max`; the DeepSeek chat/completions payload model remains `deepseek-v4-pro`.

### Delivery and schedule interfaces

Delivery remains test-recipient-only by default. Safe switches are:

- `SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT`
- `DELIVERY_TEST_RECIPIENT_MODE`
- `DELIVERY_ALLOW_NON_TEST_RECIPIENT` (rejected if true)
- `DELIVERY_SEND_EMPTY_REPORT`
- `DELIVERY_ATTACH_MARKDOWN`
- `DELIVERY_ATTACH_JSON`

SMTP and report address secrets remain: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `REPORT_SENDER_EMAIL`, and `REPORT_TEST_RECIPIENT_EMAIL`. `REPORT_RECIPIENT_EMAIL` is not required for current test-recipient-only delivery.

### Sanitized audits

Run the effective config audit:

```bash
python -m agent.main --mode config-audit
```

Run the names-only secrets/variables inventory:

```bash
python -m agent.main --mode env-inventory
```

The inventory reports canonical categories (`required_now`, `required_for_deepseek`, `required_for_delivery`, `required_for_openai_final`, `optional`, and `unused_or_delete_candidates`) and presence by name only. It never prints secret values or prefixes.

### Manual DeepSeek-only run

In GitHub Actions, use the `run_daily_with_deepseek_coarse` manual input. It enables only DeepSeek coarse for that run with `AI_FINAL_ENABLED=false`. Scheduled runs remain safe and do not inherit the manual DeepSeek input.


## Phase 7 dual-track demand classification

Daily analysis now separates source-primary demand into two independent tracks:

- **Quick Service Leads** are individual or small-business requests that may be serviced manually, such as 1688/Taobao/Alibaba buying help, supplier verification, freight forwarding/customs coordination, WeChat Pay/Alipay integration guidance, Chinese localization, and China-facing workflow setup. These leads require source-primary title/content evidence of a requester signal, a China-related serviceable workflow, and a concrete deliverable, but they do **not** need broad repeated-demand proof or product-opportunity final-filter approval.
- **Product Opportunities** remain long-term, scalable opportunities produced by the existing analyzer and the deterministic final opportunity filter. Quick service leads do not alter product scores and cannot bypass the final product-opportunity sanity filter.

Requester attribution is limited to public metadata already returned by source APIs. The report never infers real identities from usernames, keeps `contact_allowed=false` by default, and redacts public emails/phone numbers from evidence excerpts. High-risk or ambiguous account/payment/customs requests are flagged for manual compliance review; blocked categories include KYC/identity evasion, fake or sold accounts, payment fraud, credential sharing, sanctions/export-control evasion, impersonation, private-data scraping, illegal/regulated goods, and spam outreach. No automatic contacting is introduced.
