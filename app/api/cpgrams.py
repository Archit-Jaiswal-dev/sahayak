from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.rpa.credential_store import EncryptedCredentialStore
from app.rpa.session_store import EncryptedSessionStore
from app.rpa.submitter import (
    CPGRAMSSubmitter,
    AutoRenewBlocked,
    CaptchaChallenge,
    CredentialsNotStored,
    SessionNotLinked,
    StepError,
)

router = APIRouter(prefix="/v1/cpgrams", tags=["cpgrams"])


class Cookie(BaseModel):
    name: str
    value: str
    domain: str
    path: str = "/"


class LinkRequest(BaseModel):
    account_key: str
    cookies: list[Cookie]


class LinkResponse(BaseModel):
    account_key: str
    linked: bool
    expires_at: str | None = None
    message: str = ""


class UnlinkRequest(BaseModel):
    account_key: str


class CredentialsRequest(BaseModel):
    account_key: str
    username: str
    password: str


class CredentialsResponse(BaseModel):
    account_key: str
    stored: bool
    message: str = ""


class RenewRequest(BaseModel):
    account_key: str


class RenewResponse(BaseModel):
    account_key: str
    renewed: bool = True
    expires_at: str | None = None
    reason: str = ""
    # Present when a CAPTCHA/OTP pauses the renewal and the citizen must
    # answer it in-app.
    challenge: str = ""  # "captcha" | "otp" | ""
    token: str = ""
    image_b64: str = ""


class ResolveRequest(BaseModel):
    token: str
    answer: str


class UnlinkResponse(BaseModel):
    account_key: str
    unlinked: bool
    message: str = ""


class StatusResponse(BaseModel):
    account_key: str
    linked: bool
    valid: bool | None = None
    expires_at: str | None = None
    reason: str = ""


class ProfileResponse(BaseModel):
    account_key: str
    name: str = ""
    gender: str = ""
    email: str = ""
    mobile: str = ""
    phone: str = ""
    address_lines: list[str] = []
    state: str = ""
    district: str = ""
    country: str = ""
    pincode: str = ""


def _store() -> EncryptedSessionStore:
    try:
        return EncryptedSessionStore()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))


def _credential_store() -> EncryptedCredentialStore:
    try:
        return EncryptedCredentialStore()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))


def _submitter() -> CPGRAMSSubmitter:
    return CPGRAMSSubmitter(
        store=_store(),
        credential_store=_credential_store(),
    )


@router.post("/link", response_model=LinkResponse)
async def link_cpgrams(body: LinkRequest) -> LinkResponse:
    """Import a CPGRAMS session exported by the mobile WebView.

    The user logged into the real portal inside the app's WebView; this stores
    those cookies (encrypted, short-TTL) under ``account_key`` after proving
    they authenticate from the server's network.
    """
    account_key = (body.account_key or "").strip()
    if not account_key:
        raise HTTPException(status_code=400, detail="account_key is required")
    if not body.cookies:
        raise HTTPException(status_code=400, detail="cookies are required")
    submitter = _submitter()
    try:
        record = await submitter.import_session(account_key, [c.model_dump() for c in body.cookies])
    except StepError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return LinkResponse(
        account_key=account_key,
        linked=True,
        expires_at=record.expires_at.isoformat(),
        message="CPGRAMS session linked successfully.",
    )


@router.get("/status", response_model=StatusResponse)
async def cpgrams_status(account_key: str) -> StatusResponse:
    """Report whether a linked session exists and still authenticates."""
    if not (account_key or "").strip():
        raise HTTPException(status_code=400, detail="account_key is required")
    submitter = _submitter()
    result = await submitter.check_session(account_key)
    return StatusResponse(
        account_key=account_key,
        linked=result.get("linked", False),
        valid=result.get("valid"),
        expires_at=result.get("expires_at"),
        reason=result.get("reason", ""),
    )


@router.get("/profile", response_model=ProfileResponse)
async def cpgrams_profile(account_key: str) -> ProfileResponse:
    """Fetch the citizen's CPGRAMS account details from the portal.

    Requires a valid linked session. Returns the profile fields captured at
    registration (name, gender, email, mobile, address, state, district,
    pincode). Every field is best-effort and empty when the portal does not
    expose it.
    """
    if not (account_key or "").strip():
        raise HTTPException(status_code=400, detail="account_key is required")
    submitter = _submitter()
    try:
        profile = await submitter.fetch_profile(account_key)
    except SessionNotLinked as e:
        raise HTTPException(status_code=409, detail=str(e))
    except StepError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return ProfileResponse(account_key=account_key, **profile)


@router.post("/credentials", response_model=CredentialsResponse)
async def store_cpgrams_credentials(body: CredentialsRequest) -> CredentialsResponse:
    """Encrypt and store the citizen's CPGRAMS login for automatic renewal.

    Opt-in only: once stored, the server can log in again from its own network
    when the session expires, so the citizen links once and stays linked.
    """
    account_key = (body.account_key or "").strip()
    username = (body.username or "").strip()
    password = (body.password or "").strip()
    if not account_key:
        raise HTTPException(status_code=400, detail="account_key is required")
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password are required")
    submitter = _submitter()
    try:
        submitter.store_credentials(account_key, username, password)
    except StepError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return CredentialsResponse(
        account_key=account_key,
        stored=True,
        message="Credentials stored for automatic re-login.",
    )


@router.post("/renew", response_model=RenewResponse)
async def renew_cpgrams_session(body: RenewRequest) -> RenewResponse:
    """Force an automatic re-login from the server using stored credentials.

    If the portal shows a CAPTCHA or asks for an OTP, the login is paused
    server-side and a challenge (image + token) is returned for the citizen to
    solve in the app via ``/renew/resolve``.
    """
    account_key = (body.account_key or "").strip()
    if not account_key:
        raise HTTPException(status_code=400, detail="account_key is required")
    submitter = _submitter()
    try:
        result = await submitter.renew_session(account_key, interactive=True)
    except CredentialsNotStored as e:
        raise HTTPException(status_code=409, detail=str(e))
    except AutoRenewBlocked as e:
        raise HTTPException(status_code=428, detail=str(e))
    except StepError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if isinstance(result, CaptchaChallenge):
        return RenewResponse(
            account_key=account_key,
            renewed=False,
            challenge=result.kind,
            token=result.token,
            image_b64=result.image_b64,
            reason=result.message,
        )
    return RenewResponse(
        account_key=account_key,
        renewed=True,
        expires_at=result.expires_at.isoformat(),
    )


@router.post("/renew/resolve", response_model=RenewResponse)
async def resolve_cpgrams_renewal(body: ResolveRequest) -> RenewResponse:
    """Resume a paused renewal with the citizen's CAPTCHA/OTP answer."""
    token = (body.token or "").strip()
    answer = (body.answer or "").strip()
    if not token or not answer:
        raise HTTPException(status_code=400, detail="token and answer are required")
    submitter = _submitter()
    try:
        result = await submitter.resolve_captcha(token, answer)
    except StepError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if isinstance(result, CaptchaChallenge):
        return RenewResponse(
            account_key=result.account_key,
            renewed=False,
            challenge=result.kind,
            token=result.token,
            image_b64=result.image_b64,
            reason=result.message,
        )
    return RenewResponse(
        account_key=result.account_key,
        renewed=True,
        expires_at=result.expires_at.isoformat(),
    )


@router.post("/unlink", response_model=UnlinkResponse)
async def unlink_cpgrams(body: UnlinkRequest) -> UnlinkResponse:
    """Drop the stored (encrypted) CPGRAMS session for this citizen."""
    account_key = (body.account_key or "").strip()
    if not account_key:
        raise HTTPException(status_code=400, detail="account_key is required")
    store = _store()
    submitter = _submitter()
    try:
        store.delete(account_key)
        submitter.clear_credentials(account_key)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Unlink failed: {e!r}")
    return UnlinkResponse(
        account_key=account_key,
        unlinked=True,
        message="CPGRAMS session removed. No stored session remains for this account.",
    )


def _default_account() -> str:
    return settings.sahayak_default_account or "default"