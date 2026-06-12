import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


def send_report_email() -> None:
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_username = os.environ["SMTP_USERNAME"]
    smtp_password = os.environ["SMTP_PASSWORD"]
    mail_to = os.environ["REPORT_RECIPIENT"]

    mail_from = os.environ.get("MAIL_FROM", smtp_username)
    subject = os.environ.get("REPORT_SUBJECT", "每日理财消息面报告")

    report_path = Path("reports/daily-finance-report.md")
    summary_path = Path("reports/daily-finance-summary.json")

    if not report_path.exists():
        raise FileNotFoundError("reports/daily-finance-report.md 不存在，请先生成报告。")

    report_text = report_path.read_text(encoding="utf-8")

    message = EmailMessage()
    message["From"] = mail_from
    message["To"] = mail_to
    message["Subject"] = subject
    message.set_content(report_text)

    message.add_attachment(
        report_text.encode("utf-8"),
        maintype="text",
        subtype="markdown",
        filename="daily-finance-report.md",
    )

    if summary_path.exists():
        message.add_attachment(
            summary_path.read_bytes(),
            maintype="application",
            subtype="json",
            filename="daily-finance-summary.json",
        )

    with smtplib.SMTP_SSL(smtp_host, smtp_port) as smtp:
        smtp.login(smtp_username, smtp_password)
        smtp.send_message(message)


if __name__ == "__main__":
    send_report_email()
