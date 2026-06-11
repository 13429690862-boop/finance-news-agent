# Operator configuration interface

Phase 6-FIX-02 exposes safe operator-facing configuration through checked-in YAML and environment/GitHub Variables. These interfaces are intended for source/crawl tuning, AI provider dry runs, and test-recipient delivery operations without code edits.

## Hard safety boundaries

- The deterministic quality gate remains authoritative.
- The deterministic final opportunity filter remains authoritative.
- AI cannot resurrect rejected raw items, qualify metadata-only items, or bypass the final filter.
- DeepSeek receives only quality-gate-qualified raw items.
- OpenAI Responses final scoring remains disabled by default.
- Scheduled email remains test-recipient-only.
- Secret values are never printed by config or inventory audits.

## Crawled sources

Primary YAML: `configs/sources.yaml`.

Supported source names are exactly:

- `hn_algolia`
- `gdelt`
- `stackexchange`

Safe fields for each source:

- `enabled`: boolean
- `source_type`: non-empty string
- `role`: non-empty string describing source purpose
- `max_results`: non-negative integer
- `timeout_seconds`: non-negative integer
- `include_categories`: optional list of query category names from `configs/queries.yaml`

StackExchange also supports:

- `site`: default site string
- `sites`: list of StackExchange site API names

Environment/GitHub Variable overrides:

- `SOURCE_HN_ENABLED=true|false`
- `SOURCE_GDELT_ENABLED=true|false`
- `SOURCE_STACKEXCHANGE_ENABLED=true|false`

Invalid source names and invalid StackExchange site-list types fail with clear validation errors. Disabled sources are skipped cleanly, and disabling all sources does not crash the daily mode.

## Queries and categories

Primary YAML: `configs/queries.yaml`.

- Add or remove category lists under `queries`.
- Change source-specific category selection under `source_profiles`.
- To constrain a source from `configs/sources.yaml`, add `include_categories` with category names.

Example:

```yaml
stackexchange:
  enabled: true
  include_categories:
    - software_api
    - ecommerce
  sites:
    - stackoverflow
    - magento
```

## AI configuration

Primary YAML: `configs/ai_triage.yaml`.

Global safe Variables:

- `AI_TRIAGE_ENABLED`
- `AI_ALLOW_BYPASS_FINAL_FILTER` (must be false; true is rejected)
- `AI_DEFAULT_PROFILE`

DeepSeek coarse Variables:

- `AI_COARSE_ENABLED`
- `AI_COARSE_PROVIDER` (`none`, `mock`, or `deepseek`)
- `AI_COARSE_MODEL` (default raw provider id `deepseek-v4-pro`; `[1m]` is not allowed here)
- `AI_COARSE_CONTEXT_WINDOW` (`default` or `1m`; default `default`)
- `AI_COARSE_ENABLE_1M_CONTEXT` (legacy boolean convenience; default false)
- `AI_COARSE_BASE_URL` (default `https://api.deepseek.com`)
- `AI_COARSE_REASONING_EFFORT` (`none`, `low`, `medium`, `high`, `max`; default `max`)
- `AI_COARSE_TIMEOUT_SECONDS`
- `AI_COARSE_BATCH_SIZE`
- `AI_COARSE_SAMPLE_LIMIT`
- `AI_COARSE_TEMPERATURE`
- `AI_COARSE_MAX_OUTPUT_TOKENS`

OpenAI Responses final Variables:

- `AI_FINAL_ENABLED` (default false)
- `AI_FINAL_PROVIDER` (`none`, `mock`, or `openai_responses`)
- `AI_FINAL_MODEL`
- `AI_FINAL_BASE_URL`
- `AI_FINAL_TIMEOUT_SECONDS`
- `AI_FINAL_SAMPLE_LIMIT`

True Codex SDK/local agent integration is not implemented and remains:

```text
true_codex_sdk_supported=false
true_codex_sdk_enabled=false
```

## Delivery and schedule

Primary YAML: `configs/delivery.yaml`.

Safe Variables:

- `SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT`
- `DELIVERY_TEST_RECIPIENT_MODE`
- `DELIVERY_ALLOW_NON_TEST_RECIPIENT` (defaults false and true is rejected)
- `DELIVERY_SEND_EMPTY_REPORT`
- `DELIVERY_ATTACH_MARKDOWN`
- `DELIVERY_ATTACH_JSON`

Required test-recipient delivery secrets:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `REPORT_SENDER_EMAIL`
- `REPORT_TEST_RECIPIENT_EMAIL`

`REPORT_RECIPIENT_EMAIL` is not required for the current test-recipient-only flow and may be deleted if `env-inventory` reports it as unused.

## GitHub Actions manual controls

`.github/workflows/daily.yml` preserves existing inputs and adds:

- `run_deepseek_provider_check` (default false)
- `run_daily_with_deepseek_coarse` (default false)
- `ai_coarse_model` (default raw provider id `deepseek-v4-pro`)
- `ai_coarse_context_window` (default `default`; choices `default`, `1m`)
- `ai_coarse_reasoning_effort` (default `max`; choices `none`, `low`, `medium`, `high`, `max`)
- optional source enabled overrides for HN, GDELT, and StackExchange

Scheduled runs remain safe. Manual `run_daily_with_deepseek_coarse=true` enables DeepSeek coarse only for that run and keeps OpenAI final scoring disabled. Claude Code aliases such as `ANTHROPIC_MODEL=deepseek-v4-pro[1m]` are separate from the daily agent: use `AI_COARSE_MODEL=deepseek-v4-pro`, `AI_COARSE_CONTEXT_WINDOW=1m`, and `AI_COARSE_REASONING_EFFORT=max` for this project.

## Audits

```bash
python -m agent.main --mode config-audit
python -m agent.main --mode env-inventory
```

`config-audit` prints sanitized effective source, AI, and delivery configuration. `env-inventory` prints names-only required/optional/delete-candidate categories plus present/missing status for environment names available to the process.

## Rollback

1. Set `AI_TRIAGE_ENABLED=false` or `configs/ai_triage.yaml` `enabled: false`.
2. Set `SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT=false`.
3. Remove any one-run source env overrides, or restore `configs/sources.yaml` from Git.
4. Run `python -m agent.main --mode config-audit` and confirm AI/delivery are disabled as expected.
5. Run `python -m agent.main --mode daily` to confirm no-secret daily behavior.


## Phase 7 dual-track output fields

Operators should interpret the daily Markdown and JSON as two separate tracks:

- `quick_service_leads` / **Quick Service Leads**: manual-service candidates from source-primary requester evidence. These records include `lead_id`, `demand_summary`, `requested_service`, source URL, public requester attribution, urgency/simplicity/monetization scores, compliance risk, suggested service offer, suggested next step, and a redacted evidence excerpt. They are for manual review only and are not product opportunity scores.
- `product_opportunities` / **Product Opportunities**: strict Track-B opportunities that survived the existing deterministic final opportunity filter. Backward-compatible `opportunities`, `total_opportunities`, and `priority_counts` remain available.

JSON summaries also include `quick_service_lead_summary`, `product_opportunity_summary`, `requester_attribution_summary`, and `compliance_summary`. Test-recipient delivery remains test-only; the email body count line includes raw, qualified, quick-service lead, product-opportunity, and final counts.

Requester attribution uses only public source metadata returned by collectors: HN authors become public HN profile URLs, StackExchange owner display/link/user IDs are copied when the API returns them, and GDELT/news items default to requester unknown/not_applicable. Do not treat usernames as real identities, do not scrape private data, and do not auto-contact.
