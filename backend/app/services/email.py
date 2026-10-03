"""Outgoing email over SMTP (FR-32, FR-33). Credentials come from the environment only."""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(get_settings().smtp_host)


def send_email(
    recipients: list[str], subject: str, text: str, attachments: list[tuple[str, bytes, str]] | None = None
) -> bool:
    """Returns False (and logs) when SMTP is not configured; raises on delivery errors so Celery retries."""
    settings = get_settings()
    if not settings.smtp_host or not recipients:
        logger.warning("email not sent: SMTP not configured or no recipients", extra={"subject": subject})
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(text)
    for filename, data, content_type in attachments or []:
        maintype, subtype = content_type.split("/", 1)
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_starttls:
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)
    return True
