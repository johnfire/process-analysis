"""Outgoing mail over plain SMTP. A failure is reported, never raised: mail is not allowed to break a page."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from web.settings import MailSettings

log = logging.getLogger(__name__)
SMTP_TIMEOUT_SECONDS = 15


def compose_message(sender: str, recipient: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    return message


def send_mail(mail: MailSettings | None, recipient: str, subject: str, body: str) -> bool:
    """True when the server accepted the message. False when mail is unconfigured or sending failed."""
    if mail is None:
        log.warning("mail not configured; message %r to a recipient was not sent", subject)
        return False
    try:
        message = compose_message(mail.sender, recipient, subject, body)
        with smtplib.SMTP(mail.host, mail.port, timeout=SMTP_TIMEOUT_SECONDS) as server:
            if mail.uses_starttls:
                server.starttls(context=ssl.create_default_context())
            if mail.username:
                server.login(mail.username, mail.password)
            server.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        log.exception("sending %r failed", subject)
        return False


def invite_email(base_url: str, raw_token: str) -> tuple[str, str]:
    subject = "You are invited to Process Analysis"
    body = (
        "You have been invited to Process Analysis.\n\n"
        "Set your password here (the link works once and expires in 7 days):\n"
        f"{base_url}/invite/{raw_token}\n\n"
        "If you did not expect this, ignore this message.\n"
    )
    return subject, body


def reset_email(base_url: str, raw_token: str) -> tuple[str, str]:
    subject = "Reset your Process Analysis password"
    body = (
        "Someone asked to reset the password for this address.\n\n"
        f"Choose a new password here (the link works once and expires in 30 minutes):\n"
        f"{base_url}/reset/{raw_token}\n\n"
        "If this was not you, ignore this message; your password has not changed.\n"
    )
    return subject, body
