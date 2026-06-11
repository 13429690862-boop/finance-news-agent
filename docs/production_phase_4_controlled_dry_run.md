# Production Phase 4 — Controlled Dry Run

Phase 4 keeps default runs no-secret-safe and adds explicit dry-run profiles:
- `no_secret_default` (default)
- `ai_provider_dry_run`
- `delivery_test_recipient`
- `full_test_dry_run`

Commands:
- `python -m agent.main --mode secrets-audit`
- `python -m agent.main --mode secrets-audit --profile ai_provider_dry_run`
- `python -m agent.main --mode secrets-audit --profile delivery_test_recipient`
- `python -m agent.main --mode secrets-audit --profile full_test_dry_run`

Safety guarantees:
- AI provider check is connectivity/schema-only and `used_for_opportunity_qualification=false`.
- Delivery test mode only sends to `REPORT_TEST_RECIPIENT_EMAIL`.
- No fallback to production recipient in test mode.
