"""Microsoft Teams incoming-webhook messages for alerts (§18, FR-32/FR-33)."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def message_payload(title: str, text: str) -> dict[str, Any]:
    """An Adaptive Card message: accepted by Teams Workflows webhooks and by the older incoming webhooks
    (the legacy MessageCard format is not accepted by Workflows)."""
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": title,
                            "weight": "Bolder",
                            "size": "Medium",
                            "wrap": True,
                        },
                        {"type": "TextBlock", "text": text, "wrap": True},
                    ],
                },
            }
        ],
    }


def post_message(webhook_url: str, title: str, text: str) -> bool:
    if not webhook_url:
        return False
    payload = message_payload(title, text)
    response = httpx.post(webhook_url, json=payload, timeout=10.0)
    response.raise_for_status()
    return True
