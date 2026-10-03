"""HR client (Q32): list or paginated envelope responses, bearer token, errors (no network)."""

from datetime import date

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.services import hr_client


def _use(monkeypatch: pytest.MonkeyPatch, handler: httpx.MockTransport) -> None:
    monkeypatch.setattr(get_settings(), "hr_api_token", SecretStr("hr-token"))
    real = hr_client._client

    def client(base_url: str) -> httpx.Client:
        made = real(base_url)
        return httpx.Client(base_url=made.base_url, headers=made.headers, transport=handler)

    monkeypatch.setattr(hr_client, "_client", client)


def test_follows_pagination_and_sends_the_token(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json={"data": [{"employee_code": "B"}], "next": None})
        return httpx.Response(
            200,
            json={"data": [{"employee_code": "A"}], "next": "https://hr.example.com/api/employees?page=2"},
        )

    _use(monkeypatch, httpx.MockTransport(handler))
    assert [e["employee_code"] for e in hr_client.fetch_employees("https://hr.example.com/api/")] == [
        "A",
        "B",
    ]
    assert seen[0].headers["Authorization"] == "Bearer hr-token" and seen[0].url.path == "/api/employees"


def test_leaves_query_window_and_plain_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"from": "2026-09-01", "to": "2026-12-01"}
        return httpx.Response(200, json=[{"id": "L1"}, "not-a-record"])

    _use(monkeypatch, httpx.MockTransport(handler))
    assert hr_client.fetch_leaves("https://hr.example.com/api", date(2026, 9, 1), date(2026, 12, 1)) == [
        {"id": "L1"}
    ]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={}),
        httpx.Response(200, json={"unexpected": True}),
        httpx.Response(200, content=b"<html>"),
    ],
)
def test_bad_responses_raise_a_clear_error(monkeypatch: pytest.MonkeyPatch, response: httpx.Response) -> None:
    _use(monkeypatch, httpx.MockTransport(lambda request: response))
    with pytest.raises(hr_client.HrSystemError):
        hr_client.fetch_employees("https://hr.example.com/api")
