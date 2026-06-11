# Two-stage AI operator guide

The AI layer is optional and deterministic filters remain authoritative.

## Capability status

- **DeepSeek coarse triage**: supported for controlled live dry-run validation. It runs only after deterministic raw-item quality-gate acceptance.
- **OpenAI Responses final scoring**: supported as optional final enrichment, disabled by default. It runs only after deterministic final opportunity filtering.
- **True Codex SDK / local Codex agent integration**: not implemented. Current final scoring uses the OpenAI Responses API with a Codex-style prompt; it is not the Codex CLI, local Codex SDK, or a Codex agent invocation.

ChatGPT membership is not an API credential for GitHub Actions. Use provider API keys only.

## Secrets

- `DEEPSEEK_API_KEY`: required only when `coarse_stage.enabled: true` and `provider: deepseek`.
- `DEEPSEEK_BASE_URL`: optional override; defaults to `https://api.deepseek.com`.
- `AI_COARSE_MODEL`: optional raw daily-agent model override; default config is `deepseek-v4-pro`. Do not include Claude Code aliases such as `[1m]` here.
- `AI_COARSE_CONTEXT_WINDOW`: optional context-window intent metadata; allowed values are `default` and `1m`, default `default`. The current DeepSeek adapter does not send a context-window request field.
- `DEEPSEEK_REASONING_EFFORT`: optional override for the configured `reasoning_effort`; default config is `max`. The DeepSeek adapter sends this as the chat/completions `reasoning_effort` request field.
- `OPENAI_API_KEY`: required only when `final_stage.enabled: true` and `provider: openai_responses`.
- `OPENAI_BASE_URL`: optional OpenAI-compatible override.
- `OPENAI_MODEL`: optional model override; default config is `gpt-5.3-codex`.

DeepSeek-only validation does **not** require `OPENAI_API_KEY`.

## Default safe check

```bash
python -m agent.main --mode ai-provider-check
```

With default config this reports both AI stages disabled, `true_codex_sdk_supported: false`, and performs no live provider request.

## Controlled DeepSeek-only live dry-run

1. Add only `DEEPSEEK_API_KEY` as a GitHub secret or local environment variable.
2. Run the manual profile:

```bash
python -m agent.main --mode ai-provider-check --profile deepseek_coarse_dry_run --provider deepseek
```

This profile temporarily applies the following safe state for the provider check only:

- `enabled: true`
- `coarse_stage.enabled: true`
- `coarse_stage.provider: deepseek`
- `coarse_stage.model: deepseek-v4-pro`
- `coarse_stage.context_window: default`
- `coarse_stage.reasoning_effort: max`
- `coarse_stage.sample_limit: 3`
- `dry_run_provider_check: true`
- `final_stage.enabled: false`
- `final_stage.provider: none`
- `allow_ai_to_bypass_final_filter: false`

If `DEEPSEEK_API_KEY` is missing, the result is sanitized as `missing_secrets`. If present, the check sends one minimal provider-check sample, validates the JSON-only response contract, and prints sanitized status only.

## DeepSeek-only pipeline test

For a local/manual DeepSeek pipeline test, keep OpenAI final scoring disabled:

```yaml
enabled: true
dry_run: false
allow_ai_to_bypass_final_filter: false
coarse_stage:
  enabled: true
  provider: deepseek
  model: deepseek-v4-pro
  reasoning_effort: max
  sample_limit: 3
final_stage:
  enabled: false
  provider: none
```

Then run `python -m agent.main --mode daily --json-summary`. The quality gate runs first; DeepSeek receives only qualified raw items; deterministic analysis and final filtering still run; OpenAI Responses final scoring remains disabled.

## Manual test-recipient report flow

Keep delivery in test-recipient mode. Verify `REPORT_TEST_RECIPIENT_EMAIL` plus SMTP secrets before using `delivery-check`. Never enable non-test recipient delivery for dry runs.

## Rollback

Set `configs/ai_triage.yaml` top-level `enabled: false` and rerun `python -m agent.main --mode ai-provider-check`.

## Phase 6-FIX-02 env/GitHub Variable overrides

DeepSeek coarse remains disabled by default but is preconfigured for the recommended defaults:

```text
AI_COARSE_PROVIDER=deepseek
AI_COARSE_MODEL=deepseek-v4-pro
AI_COARSE_CONTEXT_WINDOW=1m
AI_COARSE_REASONING_EFFORT=max
```

Allowed reasoning efforts are `none`, `low`, `medium`, `high`, and `max`; any other value fails config validation. Allowed `AI_COARSE_CONTEXT_WINDOW` values are `default` and `1m`. `AI_ALLOW_BYPASS_FINAL_FILTER=true` is rejected.

Claude Code / Anthropic-compatible external tooling can use context aliases in Anthropic variables, for example `ANTHROPIC_MODEL=deepseek-v4-pro[1m]`, `ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro[1m]`, and `ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-pro[1m]`. Those are not daily-agent settings: daily DeepSeek coarse triage uses `AI_COARSE_MODEL=deepseek-v4-pro`, `AI_COARSE_CONTEXT_WINDOW=1m`, and `AI_COARSE_REASONING_EFFORT=max`, and the provider payload model stays `deepseek-v4-pro`.

For GitHub Actions, use `run_deepseek_provider_check=true` to run only the DeepSeek provider check, or `run_daily_with_deepseek_coarse=true` to run daily with DeepSeek coarse enabled for that manual run only. Both paths set `AI_FINAL_ENABLED=false`, so OpenAI Responses final scoring remains disabled.

Use these audits before and after changes:

```bash
python -m agent.main --mode config-audit
python -m agent.main --mode env-inventory
```

The audits are sanitized: they show provider names, model names, flags, and present/missing status by environment variable name, but never secret values.
