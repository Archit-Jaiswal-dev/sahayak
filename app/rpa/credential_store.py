"""Encrypted-at-rest CPGRAMS login credentials (for automatic session renewal).

The citizen opts in during linking: Sahayak stores their CPGRAMS
username/password (AES-256-GCM, same scheme as the session store) so the server
can log in again from its own network when a session expires or is rejected.
Credentials never leave the server and are never sent back to the app.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings
from app.rpa.session_store import SessionAuthError

AAD = b"sahayak-credentials-v1"
NONCE_LEN = 12

logger = logging.getLogger(__name__)


@dataclass
class CredentialRecord:
    """A citizen's CPGRAMS login, encrypted at rest."""

    account_key: str
    username: str
    password: str

    def as_dict(self) -> dict:
        return {
            "account_key": self.account_key,
            "username": self.username,
            "password": self.password,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CredentialRecord":
        return cls(
            account_key=data["account_key"],
            username=data["username"],
            password=data["password"],
        )


class CredentialStore:
    """Swappable storage for credentials."""

    def load(self, account_key: str) -> CredentialRecord | None: ...
    def save(self, record: CredentialRecord) -> None: ...
    def delete(self, account_key: str) -> None: ...
    def all_accounts(self) -> list[str]: ...


class EncryptedCredentialStore(CredentialStore):
    """AES-256-GCM encrypted credential store, one file per account."""

    def __init__(
        self,
        *,
        key_b64: str | None = None,
        data_dir: Path | None = None,
    ):
        key_b64 = key_b64 or settings.sahayak_session_encryption_key
        if not key_b64:
            raise ValueError("SAHAYAK_SESSION_ENCRYPTION_KEY not set.")
        try:
            key = base64.b64decode(key_b64)
        except ValueError as e:
            raise ValueError("SAHAYAK_SESSION_ENCRYPTION_KEY must be base64") from e
        if len(key) != 32:
            raise ValueError("SAHAYAK_SESSION_ENCRYPTION_KEY must decode to 32 bytes")
        self._key = key
        self._dir = (data_dir or Path("data/credentials")).resolve()
        self._dir.mkdir(parents=True, exist_ok=True)

    def load(self, account_key: str) -> CredentialRecord | None:
        path = self._path(account_key)
        if not path.exists():
            return None
        try:
            blob = json.loads(path.read_text())
            record = CredentialRecord.from_dict(self._decrypt(blob))
        except (json.JSONDecodeError, KeyError, ValueError, SessionAuthError):
            # Corrupt/foreign/tampered: never trust it. Drop.
            self.delete(account_key)
            return None
        return record

    def save(self, record: CredentialRecord) -> None:
        blob = self._encrypt(record.as_dict())
        path = self._path(record.account_key)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(blob), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    def delete(self, account_key: str) -> None:
        Path(self._path(account_key)).unlink(missing_ok=True)

    def all_accounts(self) -> list[str]:
        out: list[str] = []
        for path in self._dir.glob("*.json"):
            try:
                out.append(self._account_from_path(path))
            except Exception:
                continue
        return out

    # --- internals ---

    def _account_from_path(self, path: Path) -> str:
        b64 = path.stem + "==" if len(path.stem) % 4 else path.stem
        return base64.urlsafe_b64decode(b64).decode()

    def _path(self, account_key: str) -> Path:
        safe = base64.urlsafe_b64encode(account_key.encode()).decode().rstrip("=")
        return self._dir / f"{safe}.json"

    def _encrypt(self, payload: dict) -> dict:
        nonce = os.urandom(NONCE_LEN)
        plaintext = json.dumps(payload).encode("utf-8")
        ciphertext = AESGCM(self._key).encrypt(nonce, plaintext, AAD)
        return {
            "v": 1,
            "nonce": base64.b64encode(nonce).decode(),
            "data": base64.b64encode(ciphertext).decode(),
        }

    def _decrypt(self, blob: dict) -> dict:
        if blob.get("v") != 1:
            raise SessionAuthError("unknown credentials blob version")
        try:
            nonce = base64.b64decode(blob["nonce"])
            ciphertext = base64.b64decode(blob["data"])
        except Exception as e:
            raise SessionAuthError("malformed credentials blob") from e
        try:
            plaintext = AESGCM(self._key).decrypt(nonce, ciphertext, AAD)
        except InvalidTag as e:
            raise SessionAuthError(
                "credentials blob failed authentication (tampered or wrong key)"
            ) from e
        return json.loads(plaintext)
