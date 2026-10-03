"""Teams alert payload (§18): Adaptive Card message, posted only when a webhook is configured."""

import httpx
import pytest

from app.services import teams


def test_no_webhook_means_not_sent() -> None:
    assert teams.post_message("", "Camera offline", "Main entrance") is False


def test_posts_an_adaptive_card(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[dict[str, object]] = []

    def fake_post(url: str, json: dict[str, object], timeout: float) -> httpx.Response:
        sent.append(json)
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr(teams.httpx, "post", fake_post)
    assert teams.post_message("https://example.invalid/hook", "Camera offline", "Main entrance since 09:05")
    card = sent[0]["attachments"][0]  # type: ignore[index]
    assert card["contentType"] == "application/vnd.microsoft.card.adaptive"
    texts = [block["text"] for block in card["content"]["body"]]
    assert texts == ["Camera offline", "Main entrance since 09:05"]


def test_http_error_is_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url: str, json: dict[str, object], timeout: float) -> httpx.Response:
        return httpx.Response(400, request=httpx.Request("POST", url))

    monkeypatch.setattr(teams.httpx, "post", fake_post)
    with pytest.raises(httpx.HTTPStatusError):
        teams.post_message("https://example.invalid/hook", "t", "x")
