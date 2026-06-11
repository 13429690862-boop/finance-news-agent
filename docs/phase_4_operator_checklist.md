# Phase 4 Operator Checklist

1. Confirm defaults remain disabled (`dry_run_provider_check=false`, `dry_run_delivery_check=false`).
2. Add GitHub Secrets.
3. Run `python -m agent.main --mode secrets-audit`.
4. Run `python -m agent.main --mode ai-provider-check` only if intended.
5. Run `python -m agent.main --mode delivery-check` only with test recipient configured.
6. Confirm report artifact exists.
7. Confirm no production recipient was emailed.
8. Disable dry-run flags after test.
