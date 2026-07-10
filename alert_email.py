"""
Email a flagged tweet (screenshot + text) via Gmail SMTP using an app
password -- no OAuth/Gmail API involved.

Requires in .env:
    ALERT_EMAIL_FROM          gmail address the alert is sent from
    ALERT_EMAIL_APP_PASSWORD  app password for that account (myaccount.google.com/apppasswords)
    ALERT_EMAIL_TO            where to send the alert
"""

import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def _send(subject, body, log_label, attachment_path=None):
    sender = os.environ.get("ALERT_EMAIL_FROM")
    app_password = os.environ.get("ALERT_EMAIL_APP_PASSWORD")
    recipient = os.environ.get("ALERT_EMAIL_TO")

    if not sender or not app_password or not recipient:
        print("Skipping email alert -- ALERT_EMAIL_FROM/ALERT_EMAIL_APP_PASSWORD/ALERT_EMAIL_TO not fully set in .env")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)

    if attachment_path is not None:
        attachment_path = Path(attachment_path)
        if attachment_path.exists():
            msg.add_attachment(
                attachment_path.read_bytes(),
                maintype="image",
                subtype="png",
                filename=attachment_path.name,
            )

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(sender, app_password)
            server.send_message(msg)
        print(f"Sent {log_label} email to {recipient}")
    except Exception as e:
        print(f"Failed to send {log_label} email: {e}")


def send_threat_alert(record, flags, screenshot_path):
    tags = []
    if flags["threat_matches"]:
        tags.append("threat words: " + ", ".join(flags["threat_matches"]))
    if flags["name_matches"]:
        tags.append("names: " + ", ".join(flags["name_matches"]))

    body = (
        f"Flagged: {' | '.join(tags)}\n\n"
        f"Text: {record['text']}\n\n"
        f"URL: {record['url']}\n"
        f"Time: {record.get('timestamp')}\n"
    )
    _send(
        subject=f"[twitter_monitor] Flagged tweet from @{record['handle']}",
        body=body,
        log_label=f"alert (tweet {record['id']})",
        attachment_path=screenshot_path,
    )


def send_session_expired_alert(handle):
    body = (
        f"twitter_monitor's session cookies for @{handle} have expired "
        f"(redirected to login). Monitoring is paused until you refresh them.\n\n"
        f"Re-run auth.py or export_session.py locally (needs a display), then "
        f"copy the new storage/state.json to the server.\n"
    )
    _send(
        subject="[twitter_monitor] Session expired -- manual refresh needed",
        body=body,
        log_label="session-expired alert",
    )
