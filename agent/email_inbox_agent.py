import email
import imaplib
import os
from datetime import datetime
from email.header import decode_header
from pathlib import Path


KEYWORDS = [
    "股票",
    "基金",
    "持仓",
    "理财",
    "证券",
    "公告",
    "分红",
    "申购",
    "赎回",
    "ETF",
    "A股",
    "港股",
    "美股",
    "财报",
    "风险",
    "净值",
]


def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""

    parts = decode_header(value)
    decoded = []

    for content, charset in parts:
        if isinstance(content, bytes):
            decoded.append(content.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(content)

    return "".join(decoded)


def _extract_text(message: email.message.Message) -> str:
    if message.is_multipart():
        chunks = []
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = part.get("Content-Disposition", "")

            if content_type == "text/plain" and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    chunks.append(payload.decode(charset, errors="replace"))
        return "\n".join(chunks)

    payload = message.get_payload(decode=True)
    if not payload:
        return ""

    charset = message.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def scan_inbox() -> None:
    imap_host = os.environ["IMAP_HOST"]
    imap_port = int(os.environ.get("IMAP_PORT", "993"))
    imap_username = os.environ["IMAP_USERNAME"]
    imap_password = os.environ["IMAP_PASSWORD"]
    max_messages = int(os.environ.get("INBOX_MAX_MESSAGES", "30"))

    output_dir = Path("reports")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "inbox-finance-digest.md"

    matched_items = []

    with imaplib.IMAP4_SSL(imap_host, imap_port) as imap:
        imap.login(imap_username, imap_password)
        imap.select("INBOX")

        status, data = imap.search(None, "ALL")
        if status != "OK":
            raise RuntimeError("邮箱搜索失败")

        message_ids = data[0].split()[-max_messages:]

        for message_id in reversed(message_ids):
            status, msg_data = imap.fetch(message_id, "(RFC822)")
            if status != "OK":
                continue

            raw_message = msg_data[0][1]
            message = email.message_from_bytes(raw_message)

            subject = _decode_header_value(message.get("Subject"))
            sender = _decode_header_value(message.get("From"))
            date = _decode_header_value(message.get("Date"))
            body = _extract_text(message)

            combined = f"{subject}\n{sender}\n{body}"
            if not any(keyword.lower() in combined.lower() for keyword in KEYWORDS):
                continue

            preview = body.replace("\r", " ").replace("\n", " ").strip()
            preview = preview[:500]

            matched_items.append(
                {
                    "subject": subject,
                    "sender": sender,
                    "date": date,
                    "preview": preview,
                }
            )

    lines = [
        "# 邮箱财经信息摘要",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 命中邮件数：{len(matched_items)}",
        "",
        "## 命中邮件",
        "",
    ]

    if not matched_items:
        lines.append("最近邮件中未发现明显财经/持仓相关内容。")
    else:
        for index, item in enumerate(matched_items, start=1):
            lines.extend(
                [
                    f"### {index}. {item['subject'] or '无标题'}",
                    "",
                    f"- 发件人：{item['sender']}",
                    f"- 时间：{item['date']}",
                    "",
                    item["preview"] or "无正文预览",
                    "",
                ]
            )

    output_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    scan_inbox()
