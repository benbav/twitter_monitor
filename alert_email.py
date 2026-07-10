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


def send_threat_alert(record, flags, screenshot_path):
    sender = os.environ.get("ALERT_EMAIL_FROM")
    app_password = os.environ.get("ALERT_EMAIL_APP_PASSWORD")
    recipient = os.environ.get("ALERT_EMAIL_TO")

    if not sender or not app_password or not recipient:
        print("Skipping email alert -- ALERT_EMAIL_FROM/ALERT_EMAIL_APP_PASSWORD/ALERT_EMAIL_TO not fully set in .env")
        return

    tags = []
    if flags["threat_matches"]:
        tags.append("threat words: " + ", ".join(flags["threat_matches"]))
    if flags["name_matches"]:
        tags.append("names: " + ", ".join(flags["name_matches"]))

    msg = EmailMessage()
    msg["Subject"] = f"[twitter_monitor] Flagged tweet from @{record['handle']}"
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(
        f"Flagged: {' | '.join(tags)}\n\n"
        f"Text: {record['text']}\n\n"
        f"URL: {record['url']}\n"
        f"Time: {record.get('timestamp')}\n"
    )

    screenshot_path = Path(screenshot_path)
    if screenshot_path.exists():
        msg.add_attachment(
            screenshot_path.read_bytes(),
            maintype="image",
            subtype="png",
            filename=screenshot_path.name,
        )

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(sender, app_password)
            server.send_message(msg)
        print(f"Sent alert email for tweet {record['id']} to {recipient}")
    except Exception as e:
        print(f"Failed to send alert email for tweet {record['id']}: {e}")
