"""
Leads pipeline (codename: "origami").

Captures lead submissions from the landing page (or any external source),
persists them locally, and forwards them to Resend so we can:

  1. Notify a human inbox via a transactional email.
  2. Add the contact to a Resend Audience for ongoing CRM tracking.

The module is dependency-light on purpose: it speaks Resend over HTTP via
aiohttp, which is already a hard requirement of the gateway. No SDK install
is needed.

Environment variables (all optional — feature degrades gracefully):

  RESEND_API_KEY        Required to send mail / sync audiences. If unset,
                        leads are still persisted to disk so nothing is lost.
  RESEND_FROM_EMAIL     "from" address for notification mail
                        (default: "leads@hermes-agent.dev").
  RESEND_NOTIFY_EMAIL   Inbox that receives lead notifications.
  RESEND_AUDIENCE_ID    If set, each lead is upserted into this Resend audience.
  RESEND_REPLY_TO       Optional reply-to header for notification mail.
  LEADS_FILE            Override the on-disk JSON store
                        (default: $HERMES_HOME/leads.json).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from html import escape as html_escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]


RESEND_BASE_URL = "https://api.resend.com"
DEFAULT_FROM_EMAIL = "leads@hermes-agent.dev"
# Conservative RFC5322-lite check — we are not validating deliverability,
# only filtering obvious garbage before we hand strings to Resend.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _hermes_home() -> Path:
    """Return the directory used for Hermes runtime state."""
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env)
    return Path.home() / ".hermes"


def _default_leads_file() -> Path:
    override = os.environ.get("LEADS_FILE")
    if override:
        return Path(override)
    return _hermes_home() / "leads.json"


@dataclass
class Lead:
    """A single lead captured from the landing page or another channel."""

    id: str
    email: str
    name: Optional[str] = None
    company: Optional[str] = None
    message: Optional[str] = None
    source: str = "landing-page"
    referrer: Optional[str] = None
    user_agent: Optional[str] = None
    ip: Optional[str] = None
    created_at: float = field(default_factory=lambda: time.time())
    # Tracks downstream side-effects so we can audit & retry.
    resend_email_id: Optional[str] = None
    resend_contact_id: Optional[str] = None
    notes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_email(value: Any) -> Optional[str]:
    """Lower-case, strip whitespace, and lightly validate an email string."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    if not cleaned or not _EMAIL_RE.match(cleaned):
        return None
    if len(cleaned) > 254:  # RFC 5321 hard limit
        return None
    return cleaned


def _coerce_str(value: Any, max_len: int) -> Optional[str]:
    """Trim a free-form string to a sane max length, returning None if empty."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:max_len]


def build_lead_from_payload(
    payload: Dict[str, Any],
    *,
    request_meta: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Lead], Optional[str]]:
    """Validate a JSON payload and return (Lead, None) or (None, error)."""
    email = normalize_email(payload.get("email"))
    if not email:
        return None, "valid email is required"

    request_meta = request_meta or {}
    lead = Lead(
        id=uuid.uuid4().hex,
        email=email,
        name=_coerce_str(payload.get("name"), 200),
        company=_coerce_str(payload.get("company"), 200),
        message=_coerce_str(payload.get("message"), 4000),
        source=_coerce_str(payload.get("source"), 64) or "landing-page",
        referrer=_coerce_str(payload.get("referrer") or request_meta.get("referrer"), 500),
        user_agent=_coerce_str(request_meta.get("user_agent"), 500),
        ip=_coerce_str(request_meta.get("ip"), 64),
    )
    return lead, None


class LeadStore:
    """Append-only JSON store for captured leads.

    Writes are serialized through an asyncio lock so concurrent submissions
    do not interleave. The full list is held in-memory after the first read,
    which is fine for the modest volume a landing-page form produces.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else _default_leads_file()
        self._lock = asyncio.Lock()
        self._cache: Optional[List[Dict[str, Any]]] = None

    def _load_sync(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw) if raw.strip() else []
            if isinstance(data, list):
                return data
            logger.warning("leads file %s is not a JSON list — ignoring", self.path)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("failed to read leads file %s: %s", self.path, exc)
        return []

    def _flush_sync(self, leads: List[Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(leads, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    async def append(self, lead: Lead) -> None:
        async with self._lock:
            if self._cache is None:
                self._cache = self._load_sync()
            self._cache.append(lead.to_dict())
            self._flush_sync(self._cache)

    async def update(self, lead_id: str, **patch: Any) -> Optional[Dict[str, Any]]:
        """Patch fields on a stored lead. Returns the updated row, or None."""
        async with self._lock:
            if self._cache is None:
                self._cache = self._load_sync()
            for row in self._cache:
                if row.get("id") == lead_id:
                    row.update(patch)
                    self._flush_sync(self._cache)
                    return row
            return None

    async def list(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        async with self._lock:
            if self._cache is None:
                self._cache = self._load_sync()
            # Newest first.
            ordered = sorted(
                self._cache, key=lambda r: r.get("created_at", 0), reverse=True
            )
            if offset:
                ordered = ordered[offset:]
            return ordered[:limit]

    async def count(self) -> int:
        async with self._lock:
            if self._cache is None:
                self._cache = self._load_sync()
            return len(self._cache)


class ResendClient:
    """Tiny async client for the Resend HTTP API.

    Only covers the two endpoints we need: send transactional email and
    upsert an audience contact. Errors are logged and swallowed by the
    higher-level caller so a Resend outage cannot drop a lead.
    """

    def __init__(self, api_key: str, base_url: str = RESEND_BASE_URL) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def send_email(
        self,
        *,
        from_email: str,
        to: List[str],
        subject: str,
        html: str,
        text: Optional[str] = None,
        reply_to: Optional[str] = None,
        tags: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        if aiohttp is None:
            raise RuntimeError("aiohttp is required for ResendClient")
        body: Dict[str, Any] = {
            "from": from_email,
            "to": to,
            "subject": subject,
            "html": html,
        }
        if text:
            body["text"] = text
        if reply_to:
            body["reply_to"] = reply_to
        if tags:
            body["tags"] = tags

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{self.base_url}/emails", headers=self._headers(), json=body
            ) as resp:
                payload = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(
                        f"Resend send_email failed ({resp.status}): {payload}"
                    )
                return payload or {}

    async def add_audience_contact(
        self,
        audience_id: str,
        *,
        email: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        unsubscribed: bool = False,
    ) -> Dict[str, Any]:
        if aiohttp is None:
            raise RuntimeError("aiohttp is required for ResendClient")
        body: Dict[str, Any] = {"email": email, "unsubscribed": unsubscribed}
        if first_name:
            body["first_name"] = first_name
        if last_name:
            body["last_name"] = last_name

        url = f"{self.base_url}/audiences/{audience_id}/contacts"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=self._headers(), json=body) as resp:
                payload = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(
                        f"Resend add_audience_contact failed "
                        f"({resp.status}): {payload}"
                    )
                return payload or {}


def _split_name(full_name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Naive split of "First Last" into (first, last) for audience contacts."""
    if not full_name:
        return None, None
    parts = full_name.strip().split(None, 1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


def render_notification_email(lead: Lead) -> Tuple[str, str, str]:
    """Build (subject, html, text) for the internal lead-notification email."""
    subject = f"New Hermes lead: {lead.email}"

    rows: List[Tuple[str, str]] = [
        ("Email", lead.email),
        ("Name", lead.name or "—"),
        ("Company", lead.company or "—"),
        ("Source", lead.source),
        ("Referrer", lead.referrer or "—"),
        ("User-Agent", lead.user_agent or "—"),
        ("IP", lead.ip or "—"),
    ]

    html_rows = "".join(
        f"<tr><td style='padding:4px 12px 4px 0;color:#888;"
        f"vertical-align:top'>{html_escape(label)}</td>"
        f"<td style='padding:4px 0'>{html_escape(value)}</td></tr>"
        for label, value in rows
    )
    message_block = (
        f"<p style='margin:16px 0 4px;color:#888'>Message</p>"
        f"<pre style='white-space:pre-wrap;font-family:inherit;"
        f"background:#f6f6f6;padding:12px;border-radius:4px'>"
        f"{html_escape(lead.message)}</pre>"
        if lead.message
        else ""
    )
    html = (
        "<div style='font-family:-apple-system,Segoe UI,sans-serif;"
        "font-size:14px;line-height:1.5;color:#111'>"
        f"<h2 style='margin:0 0 16px'>New Hermes lead</h2>"
        f"<table style='border-collapse:collapse'>{html_rows}</table>"
        f"{message_block}"
        f"<p style='margin-top:24px;color:#999;font-size:12px'>"
        f"Lead ID: {html_escape(lead.id)}</p>"
        "</div>"
    )

    text_lines = [f"{label}: {value}" for label, value in rows]
    if lead.message:
        text_lines += ["", "Message:", lead.message]
    text_lines += ["", f"Lead ID: {lead.id}"]
    text = "\n".join(text_lines)

    return subject, html, text


class LeadsPipeline:
    """Coordinates persistence + Resend side-effects for new leads.

    Construct once at gateway boot and reuse. `submit()` is safe to call
    concurrently. Side-effects are best-effort: a Resend failure is logged
    on the lead row but does not abort the submission, so the API can still
    return success to the landing-page form.
    """

    def __init__(
        self,
        store: Optional[LeadStore] = None,
        *,
        api_key: Optional[str] = None,
        from_email: Optional[str] = None,
        notify_email: Optional[str] = None,
        audience_id: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> None:
        self.store = store or LeadStore()
        self.api_key = api_key if api_key is not None else os.environ.get("RESEND_API_KEY")
        self.from_email = (
            from_email
            or os.environ.get("RESEND_FROM_EMAIL")
            or DEFAULT_FROM_EMAIL
        )
        self.notify_email = notify_email or os.environ.get("RESEND_NOTIFY_EMAIL")
        self.audience_id = audience_id or os.environ.get("RESEND_AUDIENCE_ID")
        self.reply_to = reply_to or os.environ.get("RESEND_REPLY_TO")

    @property
    def resend_enabled(self) -> bool:
        return bool(self.api_key)

    def _client(self) -> Optional[ResendClient]:
        if not self.api_key:
            return None
        return ResendClient(self.api_key)

    async def submit(self, lead: Lead) -> Lead:
        """Persist + dispatch a lead. Always returns the (possibly updated) lead."""
        await self.store.append(lead)

        client = self._client()
        if client is None:
            logger.info(
                "RESEND_API_KEY not set — lead %s stored locally only",
                lead.id,
            )
            return lead

        # Notification email (only if we have somewhere to send it).
        if self.notify_email:
            try:
                subject, html, text = render_notification_email(lead)
                resp = await client.send_email(
                    from_email=self.from_email,
                    to=[self.notify_email],
                    subject=subject,
                    html=html,
                    text=text,
                    reply_to=self.reply_to or lead.email,
                    tags=[
                        {"name": "kind", "value": "lead-notification"},
                        {"name": "source", "value": lead.source},
                    ],
                )
                lead.resend_email_id = resp.get("id")
                await self.store.update(lead.id, resend_email_id=lead.resend_email_id)
            except Exception as exc:  # network / 4xx / 5xx
                logger.warning("Resend notification failed for %s: %s", lead.id, exc)
                await self.store.update(
                    lead.id, notes={"resend_email_error": str(exc)}
                )

        # Audience tracking (only if configured).
        if self.audience_id:
            first, last = _split_name(lead.name)
            try:
                resp = await client.add_audience_contact(
                    self.audience_id,
                    email=lead.email,
                    first_name=first,
                    last_name=last,
                )
                lead.resend_contact_id = resp.get("id")
                await self.store.update(
                    lead.id, resend_contact_id=lead.resend_contact_id
                )
            except Exception as exc:
                logger.warning("Resend audience sync failed for %s: %s", lead.id, exc)
                notes = {"resend_audience_error": str(exc)}
                await self.store.update(lead.id, notes=notes)

        return lead


__all__ = [
    "Lead",
    "LeadStore",
    "LeadsPipeline",
    "ResendClient",
    "build_lead_from_payload",
    "normalize_email",
    "render_notification_email",
]
