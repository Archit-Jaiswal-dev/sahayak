"""Tests for encrypted credentials and auto-renewal."""

import base64
import datetime as dt

import pytest

from app.rpa.credential_store import CredentialRecord, EncryptedCredentialStore
from app.rpa.session_store import SessionRecord
from app.rpa.submitter import CPGRAMSSubmitter, CredentialsNotStored


def _store(tmp_path) -> EncryptedCredentialStore:
    return EncryptedCredentialStore(
        key_b64=base64.b64encode(b"A" * 32).decode(),
        data_dir=tmp_path / "creds",
    )


def _record(account_key: str = "mobile-1") -> SessionRecord:
    now = dt.datetime.now(dt.timezone.utc)
    return SessionRecord(
        account_key=account_key,
        storage_state={"cookies": []},
        created_at=now,
        expires_at=now + dt.timedelta(hours=24),
    )


class FakeSessionStore:
    def __init__(self):
        self._sessions: dict[str, SessionRecord] = {}

    def load(self, account_key):
        return self._sessions.get(account_key)

    def save(self, record):
        self._sessions[record.account_key] = record

    def delete(self, account_key):
        self._sessions.pop(account_key, None)


def test_credential_roundtrip(tmp_path):
    store = _store(tmp_path)
    store.save(CredentialRecord("mobile-9876543210", "ram@example.com", "s3cret"))
    loaded = store.load("mobile-9876543210")
    assert loaded is not None
    assert loaded.username == "ram@example.com"
    assert loaded.password == "s3cret"


def test_credential_missing_returns_none(tmp_path):
    assert _store(tmp_path).load("ghost") is None


def test_credential_delete(tmp_path):
    store = _store(tmp_path)
    store.save(CredentialRecord("a", "u", "p"))
    store.delete("a")
    assert store.load("a") is None


def test_credential_tamper_is_dropped(tmp_path):
    store = _store(tmp_path)
    store.save(CredentialRecord("a", "u", "p"))
    blob_path = list((tmp_path / "creds").glob("*.json"))[0]
    blob_path.write_text(blob_path.read_text().replace("data", "dama"))
    assert store.load("a") is None


@pytest.mark.asyncio
async def test_renew_without_credentials_raises(tmp_path, monkeypatch):
    submitter = CPGRAMSSubmitter(
        credential_store=_store(tmp_path),
        store=FakeSessionStore(),
    )
    with pytest.raises(CredentialsNotStored):
        await submitter.renew_session("mobile-1")


@pytest.mark.asyncio
async def test_renew_uses_stored_credentials(tmp_path, monkeypatch):
    store = _store(tmp_path)
    store.save(CredentialRecord("mobile-1", "ram@example.com", "pw"))
    submitter = CPGRAMSSubmitter(
        credential_store=store,
        store=FakeSessionStore(),
    )

    captured = {}

    async def fake_login(
        context, page, account_key, username=None, password=None,
        allow_human=True, interactive=False,
    ):
        captured.update(
            username=username,
            password=password,
            allow_human=allow_human,
            interactive=interactive,
        )
        return _record(account_key)

    async def fake_open(page):
        return None

    monkeypatch.setattr(submitter, "_login_page", fake_login)
    monkeypatch.setattr(submitter, "_open", fake_open)

    record = await submitter.renew_session("mobile-1")
    assert captured["username"] == "ram@example.com"
    assert captured["password"] == "pw"
    assert captured["allow_human"] is False
    assert record.account_key == "mobile-1"


@pytest.mark.asyncio
async def test_ensure_session_renews_when_missing(tmp_path, monkeypatch):
    store = _store(tmp_path)
    store.save(CredentialRecord("mobile-2", "u2", "p2"))
    submitter = CPGRAMSSubmitter(
        credential_store=store,
        store=FakeSessionStore(),
    )

    async def fake_login(
        context, page, account_key, username=None, password=None,
        allow_human=True, interactive=False,
    ):
        return _record(account_key)

    async def fake_open(page):
        return None

    async def fake_probe(record):
        return True

    monkeypatch.setattr(submitter, "_login_page", fake_login)
    monkeypatch.setattr(submitter, "_open", fake_open)
    monkeypatch.setattr(submitter, "_probe_record", fake_probe)

    record = await submitter._ensure_session("mobile-2")  # noqa: SLF001
    assert record.account_key == "mobile-2"


@pytest.mark.asyncio
async def test_renew_interactive_returns_challenge(tmp_path, monkeypatch):
    from app.rpa.submitter import CaptchaChallenge

    store = _store(tmp_path)
    store.save(CredentialRecord("mobile-1", "ram@example.com", "pw"))
    submitter = CPGRAMSSubmitter(
        credential_store=store,
        store=FakeSessionStore(),
    )

    async def fake_login(context, page, account_key, **kwargs):
        return CaptchaChallenge(
            token="tok123", account_key=account_key, kind="captcha", image_b64="aGVsbG8=",
        )

    async def fake_open(page):
        return None

    monkeypatch.setattr(submitter, "_login_page", fake_login)
    monkeypatch.setattr(submitter, "_open", fake_open)
    # renew_session must NOT close the browser when pausing; assert no call.
    closed = []
    async def fake_close(p):
        closed.append(True)
    monkeypatch.setattr(submitter, "_close_pending", fake_close)

    result = await submitter.renew_session("mobile-1", interactive=True)
    assert isinstance(result, CaptchaChallenge)
    assert result.kind == "captcha"
    assert result.image_b64 == "aGVsbG8="
    assert closed == []


@pytest.mark.asyncio
async def test_renew_interactive_resolve_captcha(tmp_path, monkeypatch):
    from app.rpa.submitter import PendingLogin, _PENDING_LOGINS

    store = _store(tmp_path)
    store.save(CredentialRecord("mobile-1", "ram@example.com", "pw"))
    submitter = CPGRAMSSubmitter(
        credential_store=store,
        store=FakeSessionStore(),
    )

    page = _FakePage()
    context = _FakeContext()
    pending = PendingLogin(
        token="tok1", account_key="mobile-1", kind="captcha",
        playwright=object(), browser=object(), context=context, page=page,
        username="ram@example.com", password="pw", image_b64="aGVsbG8=",
        expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10),
    )
    _PENDING_LOGINS["tok1"] = pending

    captured = {}

    async def fake_click(page, key):
        captured["clicked"] = key

    async def fake_collect(page):
        return ""

    async def fake_close(pending):
        captured["closed"] = True

    monkeypatch.setattr(submitter, "_click", fake_click)
    monkeypatch.setattr(submitter, "_collect_login_errors", fake_collect)
    monkeypatch.setattr(submitter, "_close_pending", fake_close)

    record = await submitter.resolve_captcha("tok1", "ZXF3")
    assert captured.get("clicked") == "login_submit"
    assert captured.get("closed") is True
    assert "tok1" not in _PENDING_LOGINS
    assert record.account_key == "mobile-1"


@pytest.mark.asyncio
async def test_resolve_captcha_then_otp_chains(tmp_path, monkeypatch):
    from app.rpa.submitter import CaptchaChallenge, PendingLogin, _PENDING_LOGINS

    store = _store(tmp_path)
    store.save(CredentialRecord("mobile-1", "ram@example.com", "pw"))
    submitter = CPGRAMSSubmitter(
        credential_store=store,
        store=FakeSessionStore(),
    )

    page = _FakePage()
    page._otp_visible = True
    context = _FakeContext()
    pending = PendingLogin(
        token="tok1", account_key="mobile-1", kind="captcha",
        playwright=object(), browser=object(), context=context, page=page,
        username="ram@example.com", password="pw", image_b64="aGVsbG8=",
        expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10),
    )
    _PENDING_LOGINS["tok1"] = pending

    async def fake_click(page, key):
        pass

    async def fake_collect(page):
        return ""

    closed = []
    async def fake_close(p):
        closed.append(True)

    monkeypatch.setattr(submitter, "_click", fake_click)
    monkeypatch.setattr(submitter, "_collect_login_errors", fake_collect)
    monkeypatch.setattr(submitter, "_close_pending", fake_close)

    result = await submitter.resolve_captcha("tok1", "ABC")
    assert isinstance(result, CaptchaChallenge)
    assert result.kind == "otp"
    # New token registered; browser NOT closed yet.
    assert closed == []
    assert any(p.kind == "otp" for p in _PENDING_LOGINS.values())
    # Cleanup so the registry is empty between tests.
    for t, p in list(_PENDING_LOGINS.items()):
        _PENDING_LOGINS.pop(t, None)


class _FakePage:
    """Minimal stand-in for a Playwright page that resolve_captcha touches."""

    def __init__(self):
        self.fills = []
        self._logged_in = True
        self._otp_visible = False
        self.url = "https://pgportal.gov.in"

    def locator(self, sel):
        return _FakeLocator(self, sel)

    async def goto(self, url, wait_until=None):
        self.url = url

    async def wait_for_load_state(self, state="domcontentloaded"):
        return None

    async def inner_text(self):
        return "welcome"


class _FakeContext:
    def __init__(self):
        self._state = {"cookies": []}

    async def storage_state(self):
        return self._state


class _FakeLocator:
    def __init__(self, page, sel):
        self.page = page
        self.sel = sel

    @property
    def first(self):
        return self

    async def fill(self, value):
        self.page.fills.append((self.sel, value))

    async def count(self):
        if "otp" in self.sel:
            return 1 if self.page._otp_visible else 0
        return 1 if self.page._logged_in else 0

    async def is_visible(self):
        return True

    async def click(self, timeout=None):
        return None


async def _noop():
    return None


class CredentialLike:
    def __init__(self, account_key, username, password):
        self.account_key = account_key
        self.username = username
        self.password = password