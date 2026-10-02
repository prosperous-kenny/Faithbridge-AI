import pytest

from app.services import email as email_service


class _FakeResponse:
    def __init__(self, status_code: int, payload: str = "", json_data: dict | None = None):
        self.status_code = status_code
        self.text = payload
        self._json = json_data or {}

    def json(self) -> dict:
        return self._json


class _FakeClient:
    def __init__(self, response: _FakeResponse | Exception):
        self._response = response
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _patch(monkeypatch, client: _FakeClient):
    monkeypatch.setattr(email_service.httpx, "AsyncClient", lambda **_: client)


@pytest.mark.asyncio
async def test_send_email_success(monkeypatch):
    client = _FakeClient(_FakeResponse(200, json_data={"id": "resend-abc123"}))
    _patch(monkeypatch, client)

    result = await email_service.send_email("leader@example.org", "Subject", "Body")

    assert result.sent is True
    assert result.provider_id == "resend-abc123"
    assert client.calls[0]["json"]["to"] == ["leader@example.org"]


@pytest.mark.asyncio
async def test_send_email_reports_provider_error(monkeypatch):
    client = _FakeClient(_FakeResponse(401, payload="API key is invalid"))
    _patch(monkeypatch, client)

    result = await email_service.send_email("leader@example.org", "S", "B")

    assert result.sent is False
    assert "401" in result.detail
    assert result.provider_id is None


@pytest.mark.asyncio
async def test_send_email_handles_network_failure(monkeypatch):
    client = _FakeClient(ConnectionError("connection refused"))
    _patch(monkeypatch, client)

    result = await email_service.send_email("leader@example.org", "S", "B")

    assert result.sent is False
    assert "network error" in result.detail


@pytest.mark.asyncio
async def test_authorization_header_only_when_key_configured(monkeypatch):
    client = _FakeClient(_FakeResponse(200, json_data={"id": "x"}))
    _patch(monkeypatch, client)

    monkeypatch.setattr(email_service.settings, "resend_api_key", "")
    await email_service.send_email("a@b.org", "S", "B")
    assert "Authorization" not in client.calls[0]["headers"]

    monkeypatch.setattr(email_service.settings, "resend_api_key", "re_test_key")
    await email_service.send_email("a@b.org", "S", "B")
    assert client.calls[1]["headers"]["Authorization"] == "Bearer re_test_key"


@pytest.mark.asyncio
async def test_notify_critical_request_includes_reference(monkeypatch):
    client = _FakeClient(_FakeResponse(200, json_data={"id": "x"}))
    _patch(monkeypatch, client)

    await email_service.notify_critical_request(
        "leader@example.org", "req-0001", "Family facing eviction"
    )

    payload = client.calls[0]["json"]
    assert "req-0001" in payload["subject"]
    assert "Family facing eviction" in payload["text"]
