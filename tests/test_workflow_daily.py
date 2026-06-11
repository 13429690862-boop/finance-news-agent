from pathlib import Path

import yaml


WORKFLOW_PATH = Path('.github/workflows/daily.yml')
NO_SECRET_ENV = {
    'AI_TRIAGE_ENABLED': 'false',
    'AI_COARSE_ENABLED': 'false',
    'AI_COARSE_MODEL': '',
    'AI_COARSE_CONTEXT_WINDOW': '',
    'AI_COARSE_ENABLE_1M_CONTEXT': '',
    'AI_COARSE_REASONING_EFFORT': '',
    'AI_FINAL_ENABLED': 'false',
    'DEEPSEEK_API_KEY': '',
    'OPENAI_API_KEY': '',
    'SMTP_HOST': '',
    'SMTP_PORT': '',
    'SMTP_USERNAME': '',
    'SMTP_PASSWORD': '',
    'REPORT_SENDER_EMAIL': '',
    'REPORT_TEST_RECIPIENT_EMAIL': '',
}
PRODUCTION_RUNTIME_ENV = {
    'AI_TRIAGE_ENABLED': "${{ vars.AI_TRIAGE_ENABLED || 'false' }}",
    'AI_COARSE_ENABLED': "${{ vars.AI_COARSE_ENABLED || 'false' }}",
    'AI_COARSE_PROVIDER': "${{ vars.AI_COARSE_PROVIDER || 'deepseek' }}",
    'AI_COARSE_MODEL': "${{ vars.AI_COARSE_MODEL || 'deepseek-v4-pro' }}",
    'AI_COARSE_CONTEXT_WINDOW': "${{ vars.AI_COARSE_CONTEXT_WINDOW || 'default' }}",
    'AI_COARSE_REASONING_EFFORT': "${{ vars.AI_COARSE_REASONING_EFFORT || 'max' }}",
    'AI_FINAL_ENABLED': 'false',
    'DEEPSEEK_API_KEY': '${{ secrets.DEEPSEEK_API_KEY }}',
    'SMTP_HOST': '${{ secrets.SMTP_HOST }}',
    'SMTP_PORT': '${{ secrets.SMTP_PORT }}',
    'SMTP_USERNAME': '${{ secrets.SMTP_USERNAME }}',
    'SMTP_PASSWORD': '${{ secrets.SMTP_PASSWORD }}',
    'REPORT_SENDER_EMAIL': '${{ secrets.REPORT_SENDER_EMAIL }}',
    'REPORT_TEST_RECIPIENT_EMAIL': '${{ secrets.REPORT_TEST_RECIPIENT_EMAIL }}',
}
PRODUCTION_AI_OR_DELIVERY_ENV_KEYS = set(NO_SECRET_ENV) | {'AI_COARSE_PROVIDER'}


def workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding='utf-8')


def workflow_yaml() -> dict:
    return yaml.safe_load(workflow_text())


def daily_job() -> dict:
    return workflow_yaml()['jobs']['daily']


def step_named(name: str) -> dict:
    matches = [step for step in daily_job()['steps'] if step.get('name') == name]
    assert len(matches) == 1, name
    return matches[0]


def test_daily_workflow_exists_with_schedule_and_dispatch():
    assert WORKFLOW_PATH.exists()
    text = workflow_text()
    workflow = workflow_yaml()
    schedule = workflow[True]["schedule"]
    assert 'workflow_dispatch:' in text
    assert schedule == [{"cron": "0 0 * * *"}]
    assert "cron: '0 0 * * *'" in text


def test_daily_workflow_schedule_is_0800_asia_shanghai_utc_fallback():
    schedule = workflow_yaml()[True]["schedule"]
    assert schedule[0]["cron"] == "0 0 * * *"
    assert "timezone" not in schedule[0]


def test_daily_delivery_status_artifact_is_uploaded_when_present():
    text = workflow_text()
    assert "reports/daily-delivery-status.json" in text
    assert "name: daily-delivery-status" in text


def test_workflow_dispatch_inputs_exist_with_safe_defaults():
    text = workflow_text()
    assert 'run_delivery_check:' in text
    assert 'run_ai_provider_check:' in text
    assert 'run_full_test_dry_run:' in text
    assert 'send_report_to_test_recipient:' in text
    assert 'profile:' in text
    assert 'default: false' in text
    assert 'default: no_secret_default' in text
    assert '- no_secret_default' in text
    assert '- ai_provider_dry_run' in text
    assert '- delivery_test_recipient' in text
    assert '- full_test_dry_run' in text


def test_production_ai_and_delivery_vars_are_not_global_job_env():
    env = daily_job().get('env', {})
    leaked = PRODUCTION_AI_OR_DELIVERY_ENV_KEYS & set(env)
    assert leaked == set()
    assert env == {
        'SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT': "${{ vars.SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT || 'false' }}",
        'SOURCE_HN_ENABLED': "${{ github.event_name == 'workflow_dispatch' && inputs.source_hn_enabled || vars.SOURCE_HN_ENABLED }}",
        'SOURCE_GDELT_ENABLED': "${{ github.event_name == 'workflow_dispatch' && inputs.source_gdelt_enabled || vars.SOURCE_GDELT_ENABLED }}",
        'SOURCE_STACKEXCHANGE_ENABLED': "${{ github.event_name == 'workflow_dispatch' && inputs.source_stackexchange_enabled || vars.SOURCE_STACKEXCHANGE_ENABLED }}",
    }


def test_pytest_step_clears_production_ai_and_delivery_vars():
    step = step_named('Run pytest with no-secret defaults')
    assert step['run'] == 'pytest -q'
    assert step['env'] == NO_SECRET_ENV


def test_validation_and_audit_steps_run_no_secret_safe():
    for name in (
        'Production audit with no-secret defaults',
        'Secrets audit with no-secret defaults',
        'Config audit with no-secret defaults',
        'Environment inventory with no-secret defaults',
        'AI provider check (dry run profile)',
    ):
        step = step_named(name)
        assert step['env'] == NO_SECRET_ENV


def test_scheduled_run_can_enable_deepseek_via_runtime_github_variables():
    step = step_named('Run daily JSON summary')
    assert "github.event_name == 'schedule'" in step['if']
    assert "github.event_name == 'workflow_dispatch'" in step['if']
    assert step['env'] == PRODUCTION_RUNTIME_ENV
    assert step['run'] == 'python -m agent.main --mode daily --json-summary'


def test_production_send_steps_receive_runtime_vars_and_secrets():
    for name in (
        'Run daily JSON summary and send report (scheduled test recipient)',
        'Run daily JSON summary and send report',
    ):
        step = step_named(name)
        assert step['env'] == PRODUCTION_RUNTIME_ENV
        assert '--send-report-to-test-recipient' in step['run']


def test_ai_final_enabled_remains_false_in_all_ai_runtime_steps():
    for step in daily_job()['steps']:
        env = step.get('env') or {}
        if 'AI_FINAL_ENABLED' in env:
            assert env['AI_FINAL_ENABLED'] == 'false'


def test_scheduled_run_remains_no_secret_safe():
    text = workflow_text()
    assert "SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT: ${{ vars.SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT || 'false' }}" in text
    assert "github.event_name == 'schedule' && env.SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT != 'true'" in text
    assert '--mode daily' in text
    assert '--mode daily --json-summary' in text
    assert "github.event_name == 'workflow_dispatch' && !inputs.send_report_to_test_recipient" in text


def test_scheduled_send_requires_explicit_true_opt_in():
    text = workflow_text()
    assert "github.event_name == 'schedule' && env.SCHEDULED_SEND_REPORT_TO_TEST_RECIPIENT == 'true'" in text
    assert 'test -n "$REPORT_TEST_RECIPIENT_EMAIL"' in text
    assert '--send-report-to-test-recipient' in text


def test_manual_send_report_path_is_test_recipient_only():
    text = workflow_text()
    assert "github.event_name == 'workflow_dispatch' && inputs.send_report_to_test_recipient" in text
    assert '--send-report-to-test-recipient' in text


def test_delivery_check_only_runs_when_requested():
    text = workflow_text()
    assert 'inputs.run_delivery_check' in text
    assert "inputs.profile == 'delivery_test_recipient'" in text
    assert "inputs.profile == 'full_test_dry_run'" in text
    assert '--mode delivery-check --profile delivery_test_recipient' in text
    assert 'test -n "$REPORT_TEST_RECIPIENT_EMAIL"' in text


def test_delivery_check_step_passes_all_required_secret_env_vars():
    step = step_named('Delivery check (test recipient profile)')
    env = step['env']
    assert env['SMTP_HOST'] == '${{ secrets.SMTP_HOST }}'
    assert env['SMTP_PORT'] == '${{ secrets.SMTP_PORT }}'
    assert env['SMTP_USERNAME'] == '${{ secrets.SMTP_USERNAME }}'
    assert env['SMTP_PASSWORD'] == '${{ secrets.SMTP_PASSWORD }}'
    assert env['REPORT_SENDER_EMAIL'] == '${{ secrets.REPORT_SENDER_EMAIL }}'
    assert env['REPORT_RECIPIENT_EMAIL'] == '${{ secrets.REPORT_RECIPIENT_EMAIL }}'
    assert env['REPORT_TEST_RECIPIENT_EMAIL'] == '${{ secrets.REPORT_TEST_RECIPIENT_EMAIL }}'
    assert '--mode secrets-audit --profile delivery_test_recipient' in step['run']


def test_daily_send_path_does_not_duplicate_daily_execution():
    text = workflow_text()
    assert 'Run daily JSON summary' in text
    assert 'Run daily JSON summary and send report' in text
    assert 'python -m agent.main --mode daily\n' not in text
    assert text.count('python -m agent.main --mode daily --json-summary --send-report-to-test-recipient') == 2
    assert text.count('python -m agent.main --mode daily --json-summary') == 4


def test_scheduled_workflow_passes_deepseek_coarse_env_vars_from_github_variables_and_secrets():
    env = step_named('Run daily JSON summary')['env']
    assert env['DEEPSEEK_API_KEY'] == '${{ secrets.DEEPSEEK_API_KEY }}'
    assert env['AI_TRIAGE_ENABLED'] == "${{ vars.AI_TRIAGE_ENABLED || 'false' }}"
    assert env['AI_COARSE_ENABLED'] == "${{ vars.AI_COARSE_ENABLED || 'false' }}"
    assert env['AI_COARSE_PROVIDER'] == "${{ vars.AI_COARSE_PROVIDER || 'deepseek' }}"
    assert env['AI_COARSE_MODEL'] == "${{ vars.AI_COARSE_MODEL || 'deepseek-v4-pro' }}"
    assert env['AI_COARSE_CONTEXT_WINDOW'] == "${{ vars.AI_COARSE_CONTEXT_WINDOW || 'default' }}"
    assert env['AI_COARSE_REASONING_EFFORT'] == "${{ vars.AI_COARSE_REASONING_EFFORT || 'max' }}"
    assert env['AI_FINAL_ENABLED'] == 'false'


def test_deepseek_model_and_context_window_stay_separate_in_workflow():
    text = workflow_text()
    assert 'deepseek-v4-pro[1m]' not in text
    assert "AI_COARSE_MODEL: ${{ vars.AI_COARSE_MODEL || 'deepseek-v4-pro' }}" in text
    assert "AI_COARSE_CONTEXT_WINDOW: ${{ vars.AI_COARSE_CONTEXT_WINDOW || 'default' }}" in text
    assert 'AI_COARSE_CONTEXT_WINDOW: ${{ inputs.ai_coarse_context_window }}' in text
