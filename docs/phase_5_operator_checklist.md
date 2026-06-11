# Phase 5 Operator Checklist

1. Ensure default scheduled mode stays safe (no send unless opt-in).
2. Set repo variable `SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT=true` only when ready.
3. Confirm required secrets are configured: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `REPORT_SENDER_EMAIL`, `REPORT_TEST_RECIPIENT_EMAIL`.
4. Run manual dispatch with `send_report_to_test_recipient=true` for verification.
5. Verify artifacts:
   - `reports/daily-demand-report.md`
   - `reports/daily-demand-summary.json`
   - `reports/daily-delivery-status.json`
6. Confirm delivery remains test-recipient-only.
7. To rollback, unset or set `SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT=false`.
