# Secrets and variables inventory

Use the names-only inventory audit to understand which GitHub Secrets and Variables are required for the currently enabled features and which legacy names are safe delete candidates.

```bash
python -m agent.main --mode env-inventory
```

The command cannot read the GitHub repository secrets list directly. It reports the canonical expected names and, for names present in the current process environment, reports `present` or `missing` by name only. It never prints values or prefixes.

## Categories

### required_now

Names required by the current effective enabled features. Defaults are no-secret-safe, so this is empty unless delivery or AI stages are enabled.

### required_for_deepseek

- `DEEPSEEK_API_KEY` when DeepSeek coarse is enabled or a DeepSeek provider check is requested.

### required_for_delivery

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `REPORT_SENDER_EMAIL`
- `REPORT_TEST_RECIPIENT_EMAIL`

### required_for_openai_final

- `OPENAI_API_KEY` only when OpenAI Responses final scoring is explicitly enabled.

### optional

- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_MODEL`
- `AI_COARSE_MODEL`
- `AI_COARSE_CONTEXT_WINDOW`
- `AI_COARSE_ENABLE_1M_CONTEXT`
- `AI_COARSE_REASONING_EFFORT`
- `SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT`
- `SOURCE_HN_ENABLED`
- `SOURCE_GDELT_ENABLED`
- `SOURCE_STACKEXCHANGE_ENABLED`

### unused_or_delete_candidates

These legacy names are not required by the current safe test-recipient-only/default-disabled configuration and can be deleted if `env-inventory` reports them as unused in your environment:

- `REPORT_RECIPIENT_EMAIL`
- `COARSE_AI_API_KEY`
- `COARSE_AI_MODEL`
- `FINAL_AI_API_KEY`
- `FINAL_AI_MODEL`
- `CODEX_MODEL`
- `OPENAI_MODEL`
- `OPENAI_BASE_URL`

## Setup examples

### Enable scheduled test-recipient delivery

Set GitHub Variable:

```text
SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT=true
```

Set GitHub Secrets:

```text
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
REPORT_SENDER_EMAIL
REPORT_TEST_RECIPIENT_EMAIL
```

Do not enable non-test-recipient delivery.

### Set DeepSeek coarse defaults

```text
AI_COARSE_MODEL=deepseek-v4-pro
AI_COARSE_CONTEXT_WINDOW=1m
AI_COARSE_REASONING_EFFORT=max
```

For a manual DeepSeek-only run, use the workflow input `run_daily_with_deepseek_coarse=true` and provide `DEEPSEEK_API_KEY`. `[1m]` is allowed only in Claude Code / Anthropic-compatible aliases such as `ANTHROPIC_MODEL=deepseek-v4-pro[1m]`; it is disallowed in `AI_COARSE_MODEL`, daily-agent workflow defaults, `configs/ai_triage.yaml` model fields, and DeepSeek provider payloads. OpenAI final scoring remains disabled unless separately and explicitly configured.

## Rollback

- Remove or set `SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT=false` to stop scheduled delivery.
- Remove `AI_TRIAGE_ENABLED`/`AI_COARSE_ENABLED` overrides or set them to false.
- Keep `AI_ALLOW_BYPASS_FINAL_FILTER=false`.
- Run `python -m agent.main --mode env-inventory` and verify only expected names are required.
