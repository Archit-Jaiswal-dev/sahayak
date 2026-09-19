from __future__ import annotations

import asyncio
import base64
import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from playwright.async_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeout,
    async_playwright,
)

from app.config import settings
from app.rpa.credential_store import (
    CredentialRecord,
    CredentialStore,
    EncryptedCredentialStore,
)
from app.rpa.human import CliHumanVerifier, HumanVerifier
from app.rpa.models import GrievancePayload
from app.rpa.notifier import AlertNotifier, LogNotifier
from app.rpa.selectors import SELECTORS
from app.rpa.session_store import SessionRecord, SessionStore

logger = logging.getLogger(__name__)

REGISTRATION_ID_RE = re.compile(
    r"(?:CPGRAMS[-/\s]?)?\d{14,16}", re.IGNORECASE
)


class CaptchaError(RuntimeError):
    """The portal showed a CAPTCHA we cannot solve. Human intervention needed."""


class RegistrationNotFoundError(RuntimeError):
    """Submission looked successful but no registration ID could be scraped."""


class StepError(RuntimeError):
    """A step failed for an unexpected reason (likely portal redesign)."""


class SessionNotLinked(StepError):
    """No valid linked session for this account. Run the link flow first."""


class CredentialsNotStored(StepError):
    """No stored credentials to auto-renew with. Ask the citizen to opt in."""


class AutoRenewBlocked(StepError):
    """Auto-renewal needs human help (CAPTCHA/OTP) that we cannot do silently."""


@dataclass
class CaptchaChallenge:
    """A login that paused waiting for the citizen to solve a CAPTCHA/OTP.

    Auto-renewal keeps the (server-side) browser session alive in memory and
    returns this to the API layer so the app can show the CAPTCHA image to the
    citizen and send the solved answer back to ``resolve_captcha``.
    """

    token: str
    account_key: str
    kind: str  # "captcha" | "otp"
    image_b64: str = ""
    message: str = ""


@dataclass
class PendingLogin:
    """A paused server-side login, kept alive between API calls."""

    token: str
    account_key: str
    kind: str  # "captcha" | "otp"
    playwright: object
    browser: object
    context: object
    page: object
    username: str
    password: str
    image_b64: str = ""
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


_PENDING_LOGINS: dict[str, PendingLogin] = {}
_PENDING_TTL_MINUTES = 10


class CPGRAMSSubmitter:
    """Playwright automation against the public CPGRAMS portal.

    BRIDGE, NOT PERMANENT. Sessions are linked ONCE via a human-in-the-loop
    step (CAPTCHA + OTP belong to the citizen), stored encrypted and
    short-lived, then reused across filings until expiry.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout_ms: int = 30_000,
        notifier: AlertNotifier | None = None,
        human: HumanVerifier | None = None,
        store: SessionStore | None = None,
        credential_store: CredentialStore | None = None,
        submit_retries: int = 3,
        retry_backoff_s: float = 2.0,
    ):
        self._headless = headless
        self._timeout_ms = timeout_ms
        self._notifier = notifier or LogNotifier()
        self._human = human or CliHumanVerifier()
        self._store = store
        self._credential_store = credential_store
        self._submit_retries = submit_retries
        self._retry_backoff_s = retry_backoff_s
        self._account_key: str = ""

    async def link_session(self, account_key: str) -> SessionRecord:
        """One-time assisted login. Persists a reusable (encrypted) session."""
        self._account_key = account_key
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self._headless)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await self._open(page)
                record = await self._login_page(context, page, account_key)
                if self._store is not None:
                    self._store.save(record)
                logger.info("Linked session for account '%s' (expires %s)",
                            account_key, record.expires_at.isoformat())
                return record
            finally:
                await browser.close()

    def store_credentials(
        self, account_key: str, username: str, password: str
    ) -> None:
        """Encrypt and persist the citizen's CPGRAMS login for auto-renewal."""
        if self._credential_store is None:
            raise StepError("Credential store is not configured.")
        self._credential_store.save(
            CredentialRecord(account_key=account_key, username=username, password=password)
        )
        logger.info("Stored credentials for auto-renewal of account '%s'", account_key)

    def clear_credentials(self, account_key: str) -> None:
        if self._credential_store is not None:
            self._credential_store.delete(account_key)

    async def _ensure_session(self, account_key: str) -> SessionRecord:
        """Return a valid session, auto-renewing from stored credentials when
        the stored session is missing, expired, or rejected by the portal."""
        record = None
        if self._store is not None:
            record = self._store.load(account_key)

        valid = False
        if record is not None:
            valid = await self._probe_record(record)
            if not valid:
                logger.info(
                    "Stored session for '%s' no longer authenticates; renewing", account_key
                )
                if self._store is not None:
                    self._store.delete(account_key)

        if record is not None and valid:
            return record

        return await self.renew_session(account_key)

    async def renew_session(
        self, account_key: str, *, interactive: bool = False
    ) -> SessionRecord | CaptchaChallenge:
        """Log in again from the server using stored credentials.

        The fresh session is created on the server's IP, so it is NOT bound to
        the phone's network and works for filing. When ``interactive`` is True
        and the portal shows a CAPTCHA/OTP, the login is PAUSED (browser kept
        alive in memory) and a :class:`CaptchaChallenge` is returned so the app
        can show the image to the citizen and resume via ``resolve_captcha``.
        When ``interactive`` is False a challenge raises AutoRenewBlocked
        instead. Raises CredentialsNotStored if the citizen did not opt in.
        """
        if self._credential_store is None:
            raise CredentialsNotStored(
                f"No credential store configured; cannot auto-renew '{account_key}'."
            )
        cred = self._credential_store.load(account_key)
        if cred is None:
            raise CredentialsNotStored(
                f"No stored credentials for '{account_key}'. Opt in during "
                "linking to enable automatic re-login."
            )
        self._account_key = account_key
        self._purge_expired_pending()
        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=self._headless)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await self._open(page)
            result = await self._login_page(
                context, page, account_key, username=cred.username,
                password=cred.password, allow_human=False,
                interactive=interactive,
            )
            if isinstance(result, CaptchaChallenge):
                # Browser must stay alive so resolve_captcha can resume it.
                self._register_pending(result, p, browser, context, page,
                                       cred.username, cred.password)
                return result
            if self._store is not None:
                self._store.save(result)
            logger.info("Renewed session for account '%s' (expires %s)",
                        account_key, result.expires_at.isoformat())
            return result
        finally:
            if not isinstance(locals().get("result"), CaptchaChallenge):
                await browser.close()
                await p.stop()

    async def _probe_record(self, record: SessionRecord) -> bool:
        """Replay a stored session into a fresh context and confirm /Desk."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self._headless)
            try:
                context = await browser.new_context(storage_state=record.storage_state)
                page = await context.new_page()
                return await self._is_logged_in(page)
            finally:
                await browser.close()

    async def import_session(
        self, account_key: str, cookies: list[dict]
    ) -> SessionRecord:
        """Persist a session exported by the mobile WebView (Option A).

        The user logs into CPGRAMS inside the in-app WebView; we receive the
        portal's cookies (name/value/domain/path) and rebuild a Playwright
        storage_state from them, then prove it authenticates by replaying into
        a FRESH browser context (the exact path a later filing takes). If the
        portal rejects the imported session (wrong IP / rotated tokens), we
        raise and never store it.
        """
        storage_state = self._cookies_to_storage_state(cookies)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self._headless)
            try:
                context = await browser.new_context(storage_state=storage_state)
                page = await context.new_page()
                await self._open(page)
                if not await self._is_logged_in(page):
                    raise StepError(
                        "Imported session was rejected by the portal when "
                        "replayed from the server. The session may be bound to "
                        "the phone's IP/network. Log in again in the app and "
                        "retry, or use the assisted link flow."
                    )
            finally:
                await browser.close()
        now = datetime.now(timezone.utc)
        record = SessionRecord(
            account_key=account_key,
            storage_state=storage_state,
            created_at=now,
            expires_at=now + timedelta(hours=_ttl_hours()),
        )
        if self._store is not None:
            self._store.save(record)
        logger.info("Imported session for account '%s' (expires %s)",
                    account_key, record.expires_at.isoformat())
        return record

    def _cookies_to_storage_state(self, cookies: list[dict]) -> dict:
        """Build a Playwright storage_state from WebView-exported cookies."""
        play_cookies = []
        for c in cookies:
            domain = (c.get("domain") or "").strip().lstrip(".")
            if not domain:
                continue
            play_cookies.append({
                "name": c.get("name", ""),
                "value": c.get("value", ""),
                "domain": domain,
                "path": c.get("path") or "/",
                "expires": -1,
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            })
        return {"cookies": play_cookies, "origins": []}

    async def check_session(self, account_key: str) -> dict:
        """Verify a stored session is present, decryptable, unexpired, valid.

        When the stored session is missing or rejected, attempts an automatic
        renewal from stored credentials (when the citizen opted in).
        """
        record = None
        if self._store is not None:
            record = self._store.load(account_key)
        if record is None:
            try:
                record = await self.renew_session(account_key)
            except (CredentialsNotStored, AutoRenewBlocked, StepError):
                return {"linked": False, "reason": "no valid stored session"}
        if record is None:
            return {"linked": False, "reason": "no valid stored session"}
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self._headless)
            try:
                context = await browser.new_context(storage_state=record.storage_state)
                page = await context.new_page()
                await self._open(page)
                logged_in = await self._is_logged_in(page)
                return {"linked": True, "valid": logged_in,
                        "expires_at": record.expires_at.isoformat()}
            finally:
                await browser.close()

    async def probe_reuse(self, record: SessionRecord) -> bool:
        """The one thing that matters: does the persisted session authenticate
        when replayed into a FRESH browser context (i.e. a later filing run)?
        No second login happens here, so the single-session policy is not hit."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self._headless)
            try:
                context = await browser.new_context(storage_state=record.storage_state)
                page = await context.new_page()
                await page.goto(SELECTORS["desk_url"], wait_until="domcontentloaded")
                ok = await page.locator(SELECTORS["welcome_text"]).count() > 0
                logger.info("Reuse probe (fresh context): %s (url=%s)",
                            "OK" if ok else "FAILED", page.url)
                return ok
            finally:
                await browser.close()

    async def fetch_profile(self, account_key: str) -> dict:
        """Scrape the citizen's profile from the authenticated /EditProfile page.

        Requires a valid linked session; raises SessionNotLinked otherwise.
        Field names mirror the /Registration form (name, gender, address,
        state/district/pincode, mobile, email). CPGRAMS changes its DOM
        without notice, so every field is best-effort and empty if absent.
        """
        record = await self._ensure_session(account_key)
        if record is None:
            raise SessionNotLinked(
                f"No valid linked session for '{account_key}'. Link it first."
            )
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self._headless)
            try:
                context = await browser.new_context(storage_state=record.storage_state)
                page = await context.new_page()
                await self._open(page)
                if not await self._is_logged_in(page):
                    raise SessionNotLinked(
                        f"Stored session for '{account_key}' was rejected by the "
                        "portal. Re-link it."
                    )
                await page.goto(
                    SELECTORS["edit_profile_url"], wait_until="domcontentloaded"
                )
                profile = await self._scrape_profile(page)
                logger.info("Fetched profile for account '%s'", account_key)
                return profile
            finally:
                await browser.close()

    async def _scrape_profile(self, page: Page) -> dict:
        """Read the citizen profile form fields and selections (best-effort)."""

        def _value(sel: str) -> str:
            loc = page.locator(sel).first
            if loc.count() == 0:
                return ""
            try:
                return (loc.input_value() or "").strip()
            except Exception:  # noqa: BLE001 - field absent/hidden
                return ""

        def _option_label(sel: str, value: str) -> str:
            if not value:
                return ""
            try:
                return (
                    page.locator(f"{sel} option[value='{value}']")
                    .first.inner_text()
                    .strip()
                )
            except Exception:  # noqa: BLE001
                return value

        def _checked_gender() -> str:
            try:
                for radio_sel in SELECTORS["profile_gender_radio"].split(", "):
                    checked = page.locator(f"{radio_sel}:checked").first
                    if checked.count() > 0:
                        return (checked.get_attribute("value") or "").strip()
            except Exception:  # noqa: BLE001
                pass
            return ""

        state_value = _value(SELECTORS["profile_state_select"])
        district_value = _value(SELECTORS["profile_district_select"])
        country_value = _value(SELECTORS["profile_country_select"])

        address_lines: list[str] = []
        try:
            address_lines = [
                a.strip()
                for a in page.locator(SELECTORS["profile_address_inputs"])
                .all_input_values()
                if a.strip()
            ]
        except Exception:  # noqa: BLE001
            pass

        return {
            "name": _value(SELECTORS["profile_name_input"]),
            "gender": _checked_gender(),
            "email": _value(SELECTORS["profile_email_input"]),
            "mobile": _value(SELECTORS["profile_mobile_input"]),
            "phone": _value(SELECTORS["profile_phone_input"]),
            "address_lines": address_lines,
            "state": _option_label(SELECTORS["profile_state_select"], state_value),
            "district": _option_label(
                SELECTORS["profile_district_select"], district_value
            ),
            "country": _option_label(SELECTORS["profile_country_select"], country_value),
            "pincode": _value(SELECTORS["profile_pincode_input"]),
        }

    async def submit(self, payload: GrievancePayload, *, account_key: str) -> str:
        # Ensure a valid session first: auto-renew from stored credentials when
        # the existing one is missing, expired, or rejected by the portal.
        record = await self._ensure_session(account_key)
        if record is None:
            raise SessionNotLinked(
                f"No valid linked session for '{account_key}'. Link it first via "
                "`python -m scripts.file_grievance --link --account-key {account_key}` "
                "or in the app."
            )

        # Transient portal/network failures are retried with backoff; anything
        # that needs human action (session rejected, CAPTCHA) fails fast.
        last_exc: Exception | None = None
        for attempt in range(1, self._submit_retries + 1):
            if attempt > 1:
                await asyncio.sleep(self._retry_backoff_s * (2 ** (attempt - 2)))
                logger.info("Retrying filing (attempt %d/%d)", attempt, self._submit_retries)
            try:
                return await self._submit_once(payload, record, account_key)
            except (SessionNotLinked, CaptchaError, StepError) as exc:
                raise
            except Exception as exc:  # noqa: BLE001 - transient network/portal hiccup
                last_exc = exc
                logger.warning("Filing attempt %d failed: %r", attempt, exc)
        assert last_exc is not None
        raise last_exc

    async def _submit_once(
        self, payload: GrievancePayload, record: SessionRecord, account_key: str
    ) -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self._headless)
            context = await browser.new_context(storage_state=record.storage_state)
            page = await context.new_page()
            try:
                await self._open(page)
                if not await self._is_logged_in(page):
                    raise SessionNotLinked(
                        f"Stored session for '{account_key}' was rejected by the portal. "
                        "Re-link it."
                    )
                await self._open_grievance_form(page)
                await self._select_department(page, payload)
                await self._move_to_details(page)
                await self._fill_details(page, payload)
                await self._submit_form(page)
                reg_id = await self._scrape_registration_id(page)
                logger.info("Filed grievance %s (account=%s)", reg_id, account_key)
                return reg_id
            except Exception as exc:
                self._notifier.alert(
                    "CPGRAMS filing failed",
                    f"account={account_key} category={payload.category} error={exc!r} url={page.url}",
                )
                raise
            finally:
                await context.close()
                await browser.close()

    # --- session linking internals ---

    async def _login_page(
        self,
        context: BrowserContext,
        page: Page,
        account_key: str,
        username: str | None = None,
        password: str | None = None,
        allow_human: bool = True,
        interactive: bool = False,
    ) -> SessionRecord | CaptchaChallenge:
        username = username or settings.cpgrams_email
        password = password or settings.cpgrams_password
        if not (username and password):
            raise StepError(
                "No CPGRAMS credentials available. Provide them when linking, "
                "or set CPGRAMS_EMAIL/CPGRAMS_PASSWORD."
            )
        # The login view is a dedicated page, not a click-through.
        await page.goto(SELECTORS["signin_url"], wait_until="domcontentloaded")

        await page.fill(SELECTORS["login_username"], username)

        # The portal wipes every visible password input 100ms after load
        # ($('input[type=password]').val("")). Fill once, let that wipe fire,
        # then refill so the value survives until we click submit.
        await page.fill(SELECTORS["login_password"], password)
        await page.wait_for_timeout(350)
        if await page.input_value(SELECTORS["login_password"]) == "":
            await page.fill(SELECTORS["login_password"], password)

        if await self._has_captcha(page):
            if not allow_human and not interactive:
                raise AutoRenewBlocked(
                    "The portal is showing a CAPTCHA. Automatic renewal cannot "
                    "proceed without you — open the app and tap to re-link."
                )
            if not allow_human:
                # Pause: return a challenge; the caller keeps the browser alive
                # and the citizen solves the CAPTCHA in the app.
                return CaptchaChallenge(
                    token=secrets.token_urlsafe(24),
                    account_key=account_key,
                    kind="captcha",
                    image_b64=await self._captcha_image_b64(page),
                    message="Enter the characters shown in the image to finish renewing.",
                )
            solved = await self._human.solve_captcha(
                await page.locator(SELECTORS["captcha"]).first.screenshot()
            )
            await page.locator(SELECTORS["captcha_input"]).first.fill(solved)

        # Clicking #btnSubmit runs the portal's inline handler that hashes the
        # password client-side (sha512(sha256(pw)+salt)) into the hidden
        # #Password field, then submits. We must NOT fill #Password ourselves
        # or bypass the submit event, or the plaintext path breaks.
        await self._click(page, "login_submit")
        await page.wait_for_load_state("domcontentloaded")

        otp_field = page.locator(SELECTORS["otp_input"]).first
        if await otp_field.count() > 0 and await otp_field.is_visible():
            if not allow_human and not interactive:
                raise AutoRenewBlocked(
                    "The portal is asking for an OTP. Automatic renewal cannot "
                    "proceed without you — open the app and tap to re-link."
                )
            if not allow_human:
                return CaptchaChallenge(
                    token=secrets.token_urlsafe(24),
                    account_key=account_key,
                    kind="otp",
                    message="Enter the OTP sent to your phone to finish renewing.",
                )
            otp = await self._human.provide_otp("Enter the OTP sent to the phone")
            await otp_field.fill(otp)
            await self._click(page, "otp_submit")
            await page.wait_for_load_state("domcontentloaded")

        # Capture the session cookies RIGHT AFTER login. A later navigation to
        # the lodge page makes the portal rotate/delete session cookies, so the
        # auth ticket must be snapshotted before that.
        storage_state = await context.storage_state()

        errors = await self._collect_login_errors(page)
        # Verify the login via /Desk, which greets logged-in users; a rejected
        # login lands on /Error/Unauthorized instead. (Never verify on the
        # anonymous lodge page, which 403s — and wipes cookies — for authed
        # users.)
        await page.goto(SELECTORS["desk_url"], wait_until="domcontentloaded")
        if await page.locator(SELECTORS["welcome_text"]).count() == 0:
            raise StepError(self._login_failure_message(errors))

        now = datetime.now(timezone.utc)
        return SessionRecord(
            account_key=account_key,
            storage_state=storage_state,
            created_at=now,
            expires_at=now + timedelta(hours=_ttl_hours()),
        )

    async def _captcha_image_b64(self, page: Page) -> str:
        """Screenshot the CAPTCHA image and return it as base64."""
        try:
            shot = await page.locator(SELECTORS["captcha"]).first.screenshot()
            return base64.b64encode(shot).decode("ascii")
        except Exception:  # noqa: BLE001 - image unavailable
            return ""

    def _register_pending(
        self,
        challenge: CaptchaChallenge,
        p, browser, context, page,
        username: str,
        password: str,
    ) -> None:
        """Keep a paused login alive, keyed by its challenge token."""
        pending = PendingLogin(
            token=challenge.token,
            account_key=challenge.account_key,
            kind=challenge.kind,
            playwright=p,
            browser=browser,
            context=context,
            page=page,
            username=username,
            password=password,
            image_b64=challenge.image_b64,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=_PENDING_TTL_MINUTES),
        )
        _PENDING_LOGINS[challenge.token] = pending

    def _purge_expired_pending(self) -> None:
        now = datetime.now(timezone.utc)
        for token, pending in list(_PENDING_LOGINS.items()):
            if pending.expires_at < now:
                _PENDING_LOGINS.pop(token, None)
                asyncio.create_task(self._close_pending(pending))

    async def _close_pending(self, pending: PendingLogin) -> None:
        try:
            await pending.browser.close()
        finally:
            try:
                await pending.playwright.stop()
            except Exception:  # noqa: BLE001 - already closed
                pass

    async def resolve_captcha(
        self, token: str, answer: str
    ) -> SessionRecord | CaptchaChallenge:
        """Resume a paused login with the citizen's CAPTCHA/OTP answer.

        The browser has been kept alive in ``_PENDING_LOGINS`` since the login
        paused. Fills the challenge, submits, and finishes the login. Returns
        the saved SessionRecord, or another CaptchaChallenge if the portal
        presents a further step (e.g. OTP after CAPTCHA).
        """
        self._purge_expired_pending()
        pending = _PENDING_LOGINS.pop(token, None)
        if pending is None:
            raise StepError(
                "That renewal challenge expired. Open the app and renew again."
            )
        chained = False
        try:
            page = pending.page
            if pending.kind == "captcha":
                await page.locator(SELECTORS["captcha_input"]).first.fill(answer)
                await self._click(page, "login_submit")
                await page.wait_for_load_state("domcontentloaded")
                # OTP may follow a successful CAPTCHA.
                otp_field = page.locator(SELECTORS["otp_input"]).first
                if await otp_field.count() > 0 and await otp_field.is_visible():
                    ch = CaptchaChallenge(
                        token=secrets.token_urlsafe(24),
                        account_key=pending.account_key,
                        kind="otp",
                        message="Enter the OTP sent to your phone to finish renewing.",
                    )
                    self._register_pending(
                        ch, pending.playwright, pending.browser,
                        pending.context, page, pending.username, pending.password,
                    )
                    chained = True
                    return ch
            else:  # otp
                await page.locator(SELECTORS["otp_input"]).first.fill(answer)
                await self._click(page, "otp_submit")
                await page.wait_for_load_state("domcontentloaded")

            storage_state = await pending.context.storage_state()
            errors = await self._collect_login_errors(page)
            await page.goto(SELECTORS["desk_url"], wait_until="domcontentloaded")
            if await page.locator(SELECTORS["welcome_text"]).count() == 0:
                raise StepError(self._login_failure_message(errors))
            now = datetime.now(timezone.utc)
            record = SessionRecord(
                account_key=pending.account_key,
                storage_state=storage_state,
                created_at=now,
                expires_at=now + timedelta(hours=_ttl_hours()),
            )
            if self._store is not None:
                self._store.save(record)
            logger.info("Resolved renewal for account '%s' (expires %s)",
                        pending.account_key, record.expires_at.isoformat())
            return record
        finally:
            if not chained:
                await self._close_pending(pending)

    async def _collect_login_errors(self, page: Page) -> str:
        """Best-effort dump of ASP.NET MVC validation messages after login."""
        texts = await page.eval_on_selector_all(
            ".validation-summary-errors li, .field-validation-error, "
            "[class*='error' i][role='alert'], [class*='error' i].err-txt",
            "els => els.map(e => (e.textContent || '').trim()).filter(Boolean)",
        )
        for t in texts:
            logger.info("Portal login error: %s", t)
        return " | ".join(texts)[:300]

    def _login_failure_message(self, errors: str) -> str:
        hint = ""
        if errors and "another session" in errors.lower():
            hint = " The portal reported a concurrent session for this user. " \
                   "Log out of CPGRAMS on all devices/browsers, wait a few " \
                   "minutes for the server-side session to expire, and retry --link."
        elif errors:
            hint = f" Portal says: {errors}."
        else:
            hint = " No error text found."
        return (
            "Login was not accepted by the portal."
            + hint
            + " Check CPGRAMS_EMAIL/CPGRAMS_PASSWORD if this persists."
        )

    async def _is_logged_in(self, page: Page) -> bool:
        # /Desk is auth-aware: "Welcome : <name>" when logged in, 403 -> 
        # /Error/Unauthorized when not. This is the only reliable signal.
        await page.goto(SELECTORS["desk_url"], wait_until="domcontentloaded")
        return await page.locator(SELECTORS["welcome_text"]).count() > 0

    # --- filing steps ---

    async def _open(self, page: Page) -> None:
        logger.info("Opening CPGRAMS portal")
        await page.goto("https://pgportal.gov.in", wait_until="domcontentloaded")

    async def _open_grievance_form(self, page: Page) -> None:
        # Establish the authenticated chain via /Desk (we verified direct
        # navigation to /NewGrievance 403s and wipes cookies; the desk nav-link
        # carries the right referer), then walk the terms gate.
        await page.goto(SELECTORS["desk_url"], wait_until="domcontentloaded")
        await page.locator("a[href*='NewGrievance']").first.click()
        await page.wait_for_load_state("domcontentloaded")
        if await page.locator(SELECTORS["terms_checkbox"]).count():
            await page.locator(SELECTORS["terms_checkbox"]).check()
            await page.locator(SELECTORS["terms_submit"]).click()
            await page.wait_for_load_state("domcontentloaded")

    async def _select_department(self, page: Page, payload: GrievancePayload) -> None:
        # Organisation pick from the verified questionnaire, then walk the
        # level-by-level category selects. Selection is based on the citizen's
        # described category (fuzzy match), else the first meaningful option.
        await self._select_org(page, payload)
        await self._walk_categories(page, payload)

    async def _select_org(self, page: Page, payload: GrievancePayload) -> None:
        org = page.locator(SELECTORS["org_select"]).first
        if await org.count() == 0:
            raise StepError(f"Organisation select not found: {SELECTORS['org_select']}")
        label = await _match_choice(org, payload.routed_ministry, payload.category)
        if label:
            await org.select_option(label=label)
            await page.wait_for_timeout(800)
        await page.wait_for_load_state("domcontentloaded")

    async def _walk_categories(self, page: Page, payload: GrievancePayload) -> None:
        # Keep choosing an option in the deepest still-empty category select
        # until the portal reveals the Remarks box. Selection is fuzzy against
        # the citizen's category, else the first meaningful option.
        for _ in range(6):
            picked = False
            selects = await page.locator(SELECTORS["category_level_selects"]).all()
            for sel in selects:
                if await sel.input_value():
                    continue
                label = await _match_choice(sel, payload.category)
                if not label:
                    continue
                await sel.select_option(label=label)
                picked = True
                await page.wait_for_timeout(600)
                await page.wait_for_load_state("domcontentloaded")
                break  # DOM changed; next iteration resolves any new level
            if not picked:
                break
        remarks = page.locator(SELECTORS["remarks_textarea"]).first
        if await remarks.count() == 0:
            raise StepError("Remarks textarea did not appear after category selection.")
        await remarks.fill(_compose_description(payload))

    async def _fill_details(self, page: Page, payload: GrievancePayload) -> None:
        # Pincode FIRST: CPGRAMS auto-fills district/city from it. State is
        # matched from the location string when possible.
        await page.locator(SELECTORS["pincode_input"]).fill(_extract_pincode(payload.location))
        await _pick_select_contains(page, SELECTORS["country_select"], "India", optional=True)
        await _pick_state(page, payload.location)
        text = await page.locator(SELECTORS["description_textarea"]).first.input_value()
        if not text:
            await page.locator(SELECTORS["description_textarea"]).first.fill(_compose_description(payload))
        await page.locator(SELECTORS["name_input"]).fill(payload.name)
        await _pick_gender(page)
        address = (payload.location or "").strip()
        await page.locator(SELECTORS["address1_input"]).fill(address)
        if re.fullmatch(r"\d{10}", payload.contact or ""):
            await page.locator(SELECTORS["mobile_input"]).fill(payload.contact)

    async def _move_to_details(self, page: Page) -> None:
        nxt = page.locator(SELECTORS["btn_next"]).first
        if await nxt.count():
            await page.locator(SELECTORS["btn_next"]).click()
            await page.wait_for_load_state("domcontentloaded")

    async def _submit_form(self, page: Page) -> None:
        # The Details page carries a real CAPTCHA before the final Submit;
        # that is a human-in-the-loop step, exactly like login.
        captcha_img = page.locator("img[src*='aptcha' i], img[id*='aptcha' i]").first
        if await captcha_img.count() and await page.locator(SELECTORS["final_captcha_input"]).count():
            solved = await self._human.solve_captcha(await captcha_img.screenshot())
            await page.locator(SELECTORS["final_captcha_input"]).fill(solved)
        await self._click(page, "submit_button")
        await page.wait_for_load_state("domcontentloaded")

    async def _scrape_registration_id(self, page: Page) -> str:
        text = await page.locator("body").inner_text()
        match = REGISTRATION_ID_RE.search(text)
        if not match:
            raise RegistrationNotFoundError(
                f"No registration ID found on confirmation page. Snippet: {text[:300]}"
            )
        return match.group(0)

    # --- helpers ---

    async def _has_captcha(self, page: Page) -> bool:
        return await page.locator(SELECTORS["captcha"]).count() > 0

    async def _click(self, page: Page, key: str) -> None:
        locator = page.locator(SELECTORS[key]).first
        try:
            await locator.click(timeout=self._timeout_ms)
        except PlaywrightTimeout as e:
            raise StepError(
                f"Could not click '{key}' (selector: {SELECTORS[key]}). "
                "Portal may have changed."
            ) from e

    async def _select_option(
        self, page: Page, key: str, value: str | None, optional: bool = False
    ) -> None:
        locator = page.locator(SELECTORS[key]).first
        if await locator.count() == 0:
            if optional:
                logger.info("Selector '%s' not present; skipping (optional).", key)
                return
            raise StepError(f"Selector '{key}' not found: {SELECTORS[key]}")
        if value is None:
            return
        try:
            await locator.select_option(label=value)
        except PlaywrightTimeout:
            raise StepError(f"Timeout selecting '{key}' = {value}")
        except Exception as e:
            if optional:
                logger.info("Could not select '%s' = %s (optional): %s", key, value, e)
                return
            raise StepError(f"Could not select '{key}' = {value}: {e!r}")


def _ttl_hours() -> float:
    ttl = settings.sahayak_session_ttl_hours
    return ttl if ttl and ttl > 0 else 24.0


def _extract_pincode(location: str) -> str:
    match = re.search(r"\b\d{6}\b", location)
    return match.group(0) if match else ""


def _compose_description(payload: GrievancePayload) -> str:
    return (
        f"Category: {payload.category}\n"
        f"Description: {payload.description}\n"
        f"Date of issue: {payload.date}\n"
        f"Complainant: {payload.name}, {payload.contact}"
    )[:1000]


async def _meaningful_options(locator) -> list[str]:
    """Dropdown texts, striping 'Please select...' placeholders."""
    opts = await locator.locator("option").evaluate_all("els => els.map(e => e.text)")
    out: list[str] = []
    for t in opts:
        t = (t or "").strip()
        if not t:
            continue
        if re.search(r"select|choose|please|^[-—\s]+$", t, re.I):
            continue
        out.append(t)
    return out


async def _match_choice(locator, *candidates: str) -> str:
    """First option whose text contains/equals any candidate, else first."""
    opts = await _meaningful_options(locator)
    if not opts:
        return ""
    for cand in candidates or []:
        c = (cand or "").strip().lower()
        if not c:
            continue
        for t in opts:
            if c in t.lower() or t.lower() in c:
                return t
    return opts[0]


async def _pick_gender(page: Page) -> None:
    radios = page.locator("input[name='Gender']")
    if any(await radios.evaluate_all("els => els.map(e => e.checked)")):
        return
    if await radios.count():
        await radios.nth(0).check(force=True)


async def _pick_select_contains(page: Page, key: str, text: str, optional: bool = True) -> None:
    loc = page.locator(SELECTORS[key]).first
    if await loc.count() == 0:
        if optional:
            return
        raise StepError(f"Selector '{key}' not found: {SELECTORS[key]}")
    try:
        await loc.select_option(label=text)
    except Exception:
        if not optional:
            raise
        logger.info("Could not select '%s' = %s (optional); skipped.", key, text)


async def _pick_state(page: Page, location: str) -> None:
    loc = page.locator(SELECTORS["state_select"]).first
    if await loc.count() == 0:
        return
    loc_l = (location or "").strip().lower()
    if not loc_l:
        return
    for t in await _meaningful_options(loc):
        tl = t.lower()
        if tl in loc_l or loc_l in tl:
            try:
                await loc.select_option(label=t)
            except Exception:
                logger.info("State select failed for %r; leaving default.", t)
            return