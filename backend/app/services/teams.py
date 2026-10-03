"""Microsoft Teams incoming-webhook messages for alerts (§18, FR-32/FR-33)."""

import logging

import httpx

logger = logging.getLogger(__name__)


def post_message(webhook_url: str, title: str, text: str) -> bool:
    if not webhook_url:
        return False
    payload = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": title,
        "title": title,
        "text": text,
    }
    response = httpx.post(webhook_url, json=payload, timeout=10.0)
    response.raise_for_status()
    return True
