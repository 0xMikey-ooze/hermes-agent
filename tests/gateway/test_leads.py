"""Tests for gateway/leads.py and the /api/leads endpoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gateway.leads import (
    Lead,
    LeadStore,
    LeadsPipeline,
    build_lead_from_payload,
    normalize_email,
    render_notification_email,
)

pytest_plugins = ["pytest_asyncio"]


# ---------------------------------------------------------------------------
# normalize_email
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("foo@bar.com", "foo@bar.com"),
        ("  Foo@Bar.COM  ", "foo@bar.com"),
        ("a.b+tag@c.co.uk", "a.b+tag@c.co.uk"),
    ],
)
def test_normalize_email_accepts_valid(raw, expected):
    assert normalize_email(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "not-an-email", "no@dot", "@nothing.com", "spaces in@addr.com", None, 42],
)
def test_normalize_email_rejects_invalid(raw):
    assert normalize_email(raw) is None


# ---------------------------------------------------------------------------
# build_lead_from_payload
# ---------------------------------------------------------------------------

def test_build_lead_requires_email():
    lead, err = build_lead_from_payload({})
    assert lead is None
    assert err and "email" in err


def test_build_lead_strips_and_truncates():
    huge = "x" * 10_000
    lead, err = build_lead_from_payload(
        {"email": "USER@example.com", "name": " Jane ", "message": huge},
    )
    assert err is None
    assert lead is not None
    assert lead.email == "user@example.com"
    assert lead.name == "Jane"
    assert lead.message is not None
    # message coerced to <= 4000 chars
    assert len(lead.message) == 4000


def test_build_lead_pulls_request_meta():
    lead, _ = build_lead_from_payload(
        {"email": "a@b.co"},
        request_meta={
            "user_agent": "Mozilla/5.0",
            "referrer": "https://example.com/r",
            "ip": "203.0.113.10",
        },
    )
    assert lead is not None
    assert lead.user_agent == "Mozilla/5.0"
    assert lead.referrer == "https://example.com/r"
    assert lead.ip == "203.0.113.10"
    assert lead.source == "landing-page"


# ---------------------------------------------------------------------------
# LeadStore
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lead_store_persists_to_disk(tmp_path):
    store = LeadStore(path=tmp_path / "leads.json")
    lead = Lead(id="abc", email="x@y.co")
    await store.append(lead)

    on_disk = json.loads((tmp_path / "leads.json").read_text())
    assert len(on_disk) == 1
    assert on_disk[0]["id"] == "abc"
    assert on_disk[0]["email"] == "x@y.co"


@pytest.mark.asyncio
async def test_lead_store_update_patches_row(tmp_path):
    store = LeadStore(path=tmp_path / "leads.json")
    await store.append(Lead(id="abc", email="x@y.co"))

    updated = await store.update("abc", resend_email_id="resend_123")
    assert updated is not None
    assert updated["resend_email_id"] == "resend_123"

    on_disk = json.loads((tmp_path / "leads.json").read_text())
    assert on_disk[0]["resend_email_id"] == "resend_123"


@pytest.mark.asyncio
async def test_lead_store_list_newest_first(tmp_path):
    store = LeadStore(path=tmp_path / "leads.json")
    await store.append(Lead(id="a", email="a@x.co", created_at=1.0))
    await store.append(Lead(id="b", email="b@x.co", created_at=3.0))
    await store.append(Lead(id="c", email="c@x.co", created_at=2.0))

    rows = await store.list(limit=10)
    assert [r["id"] for r in rows] == ["b", "c", "a"]
    assert await store.count() == 3


# ---------------------------------------------------------------------------
# render_notification_email
# ---------------------------------------------------------------------------

def test_render_notification_email_escapes_html():
    lead = Lead(
        id="abc",
        email="x@y.co",
        name="<script>alert(1)</script>",
        message="hi & bye",
    )
    subject, html, text = render_notification_email(lead)
    assert "x@y.co" in subject
    # tag chars must be escaped
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "hi &amp; bye" in html
    # plain text retains the original message
    assert "hi & bye" in text


# ---------------------------------------------------------------------------
# LeadsPipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_persists_without_resend(tmp_path, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    pipeline = LeadsPipeline(store=LeadStore(path=tmp_path / "leads.json"))
    assert pipeline.resend_enabled is False

    lead = Lead(id="abc", email="x@y.co")
    out = await pipeline.submit(lead)

    assert out.resend_email_id is None
    assert out.resend_contact_id is None
    rows = json.loads((tmp_path / "leads.json").read_text())
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_pipeline_sends_email_and_syncs_audience(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_NOTIFY_EMAIL", "ops@hermes.dev")
    monkeypatch.setenv("RESEND_AUDIENCE_ID", "aud_123")

    pipeline = LeadsPipeline(store=LeadStore(path=tmp_path / "leads.json"))

    fake_client = MagicMock()
    fake_client.send_email = AsyncMock(return_value={"id": "email_xyz"})
    fake_client.add_audience_contact = AsyncMock(return_value={"id": "contact_xyz"})

    with patch.object(pipeline, "_client", return_value=fake_client):
        lead = Lead(id="abc", email="jane@example.com", name="Jane Doe")
        out = await pipeline.submit(lead)

    fake_client.send_email.assert_awaited_once()
    fake_client.add_audience_contact.assert_awaited_once()
    contact_kwargs = fake_client.add_audience_contact.await_args.kwargs
    assert contact_kwargs["email"] == "jane@example.com"
    assert contact_kwargs["first_name"] == "Jane"
    assert contact_kwargs["last_name"] == "Doe"

    assert out.resend_email_id == "email_xyz"
    assert out.resend_contact_id == "contact_xyz"

    on_disk = json.loads((tmp_path / "leads.json").read_text())
    assert on_disk[0]["resend_email_id"] == "email_xyz"
    assert on_disk[0]["resend_contact_id"] == "contact_xyz"


@pytest.mark.asyncio
async def test_pipeline_swallows_resend_errors(tmp_path, monkeypatch):
    """A Resend outage must never lose a lead."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_NOTIFY_EMAIL", "ops@hermes.dev")

    pipeline = LeadsPipeline(store=LeadStore(path=tmp_path / "leads.json"))

    fake_client = MagicMock()
    fake_client.send_email = AsyncMock(side_effect=RuntimeError("boom"))
    fake_client.add_audience_contact = AsyncMock(return_value={"id": "c"})

    with patch.object(pipeline, "_client", return_value=fake_client):
        out = await pipeline.submit(Lead(id="abc", email="x@y.co"))

    assert out.resend_email_id is None  # send failed
    on_disk = json.loads((tmp_path / "leads.json").read_text())
    assert on_disk[0]["notes"]["resend_email_error"]


# ---------------------------------------------------------------------------
# /api/leads endpoint
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_agi_client():
    return MagicMock()


def _make_api(tmp_path, monkeypatch):
    """Build a HermesWebAPI with an isolated leads store."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("LEADS_FILE", str(tmp_path / "leads.json"))
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)

    from gateway.web_api import HermesWebAPI

    return HermesWebAPI(agi_client=MagicMock(), config={})


@pytest.mark.asyncio
async def test_post_leads_persists_lead(tmp_path, monkeypatch, aiohttp_client):
    api = _make_api(tmp_path, monkeypatch)
    client = await aiohttp_client(api.create_app())

    resp = await client.post(
        "/api/leads", json={"email": "user@example.com", "name": "Alice"}
    )
    assert resp.status == 201
    body = await resp.json()
    assert body["ok"] is True
    assert body["id"]

    rows = json.loads((tmp_path / "leads.json").read_text())
    assert len(rows) == 1
    assert rows[0]["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_post_leads_rejects_missing_email(tmp_path, monkeypatch, aiohttp_client):
    api = _make_api(tmp_path, monkeypatch)
    client = await aiohttp_client(api.create_app())

    resp = await client.post("/api/leads", json={"name": "Alice"})
    assert resp.status == 400
    body = await resp.json()
    assert "email" in body["error"].lower()


@pytest.mark.asyncio
async def test_post_leads_honeypot_returns_ok_but_drops(tmp_path, monkeypatch, aiohttp_client):
    api = _make_api(tmp_path, monkeypatch)
    client = await aiohttp_client(api.create_app())

    resp = await client.post(
        "/api/leads", json={"email": "bot@spam.co", "website": "http://spam"}
    )
    # Honeypot pretends to succeed so bots don't retry.
    assert resp.status == 200
    body = await resp.json()
    assert body["ok"] is True
    # ...but the lead must NOT be persisted.
    assert not (tmp_path / "leads.json").exists()


@pytest.mark.asyncio
async def test_post_leads_rate_limit(tmp_path, monkeypatch, aiohttp_client):
    api = _make_api(tmp_path, monkeypatch)
    # Tighten the limit so the test is fast.
    api._LEAD_RATE_MAX_PER_WINDOW = 2
    client = await aiohttp_client(api.create_app())

    payload = {"email": "user@example.com"}
    headers = {"X-Forwarded-For": "198.51.100.7"}
    r1 = await client.post("/api/leads", json=payload, headers=headers)
    r2 = await client.post("/api/leads", json=payload, headers=headers)
    r3 = await client.post("/api/leads", json=payload, headers=headers)
    assert r1.status == 201
    assert r2.status == 201
    assert r3.status == 429


@pytest.mark.asyncio
async def test_post_leads_skips_dashboard_auth(tmp_path, monkeypatch, aiohttp_client):
    """Public form must work even with DASHBOARD_API_KEY set."""
    monkeypatch.setenv("DASHBOARD_API_KEY", "secret")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("LEADS_FILE", str(tmp_path / "leads.json"))
    monkeypatch.delenv("RESEND_API_KEY", raising=False)

    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=MagicMock(), config={})
    client = await aiohttp_client(api.create_app())

    resp = await client.post("/api/leads", json={"email": "user@example.com"})
    assert resp.status == 201

    # The GET endpoint, in contrast, must still require the key.
    resp_get = await client.get("/api/leads")
    assert resp_get.status == 401


@pytest.mark.asyncio
async def test_get_leads_returns_stored_rows(tmp_path, monkeypatch, aiohttp_client):
    api = _make_api(tmp_path, monkeypatch)
    client = await aiohttp_client(api.create_app())

    await client.post("/api/leads", json={"email": "a@x.co"})
    await client.post("/api/leads", json={"email": "b@x.co"})

    resp = await client.get("/api/leads")
    assert resp.status == 200
    body = await resp.json()
    assert body["total"] == 2
    assert body["resend_enabled"] is False
    assert {row["email"] for row in body["leads"]} == {"a@x.co", "b@x.co"}
