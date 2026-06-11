# Phase 3 Controlled Secrets Dry-Run

Run no-secret daily:
- `python -m agent.main --mode daily --json-summary`

Run secrets audit:
- `python -m agent.main --mode secrets-audit`

Safety guarantees:
- Real AI calls require `enabled=true` + `dry_run_provider_check=true` + secrets.
- Real email sends require `enabled=true` + SMTP secrets + `test_recipient_mode=true`.
- Final deterministic filter is always enforced.
