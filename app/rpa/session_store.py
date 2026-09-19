from __future__ import annotations

import base64
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

AAD = b"sahayak-session-v1"
NONCE_LEN = 12

logger = logging.getLogger(__name__)


def generate_key() -> str:
    """Generate a random 32-byte base64 key for SAHAYAK_SESSION_ENCRYPTION_KEY."""
    return base64.b64encode(secrets.token_bytes(32)).decode()


class SessionAuthError(RuntimeError):
    """Decryption failed or the blob was tampered with."""


@dataclass
class SessionRecord:
    """An authenticated CPGRAMS session (cookies + storage) plus policy metadata."""

    account_key: str
    storage_state: dict
    created_at: datetime
    expires_at: datetime

    @property
    def expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    def as_dict(self) -> dict:
        return {
            "account_key": self.account_key,
            "storage_state": self.storage_state,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionRecord":
        return cls(
            account_key=data["account_key"],
            storage_state=data["storage_state"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )


class SessionStore:
    """Swappable storage backend (file today, Redis/KMS with the API layer)."""

    def load(self, account_key: str) -> SessionRecord | None: ...
    def save(self, record: SessionRecord) -> None: ...
    def delete(self, account_key: str) -> None: ...


class EncryptedSessionStore(SessionStore):
    """Encrypted-at-rest session store.

    - AES-256-GCM authenticated encryption (tamper detection).
    - One file per account, atomic writes, 0600 permissions.
    - Conservative TTL: records are dropped as soon as they expire; a fresh
      human-assisted link is required to renew (revocation by expiry).
    """

    def __init__(
        self,
        *,
        key_b64: str | None = None,
        data_dir: Path | None = None,
    ):
        key_b64 = key_b64 or settings.sahayak_session_encryption_key
        if not key_b64:
            raise ValueError(
                "SAHAYAK_SESSION_ENCRYPTION_KEY not set. Generate one with:\n"
                "  python -m app.rpa.session_store --gen-key"
            )
        try:
            key = base64.b64decode(key_b64)
        except ValueError as e:
            raise ValueError("SAHAYAK_SESSION_ENCRYPTION_KEY must be base64") from e
        if len(key) != 32:
            raise ValueError("SAHAYAK_SESSION_ENCRYPTION_KEY must decode to 32 bytes")
        self._key = key
        self._dir = (data_dir or Path("data/sessions")).resolve()
        self._dir.mkdir(parents=True, exist_ok=True)

    # --- public API ---

    def load(self, account_key: str) -> SessionRecord | None:
        path = self._path(account_key)
        if not path.exists():
            return None
        try:
            blob = json.loads(path.read_text())
            record = SessionRecord.from_dict(self._decrypt(blob))
        except (json.JSONDecodeError, KeyError, ValueError):
            # Corrupt/foreign file: drop it. Best to re-link than to guess.
            self.delete(account_key)
            return None
        except SessionAuthError as e:
            # Tampered or wrong key: never trust it. Drop + log; treat as unlinked.
            logger.warning("Dropping session for '%s': %s", account_key, e)
            self.delete(account_key)
            return None
        if record.expired:
            self.delete(account_key)
            return None
        return record

    def save(self, record: SessionRecord) -> None:
        if record.expires_at <= datetime.now(timezone.utc):
            raise ValueError("refusing to store an already-expired session")
        blob = self._encrypt(record.as_dict())
        path = self._path(record.account_key)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(blob), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    def delete(self, account_key: str) -> None:
        Path(self._path(account_key)).unlink(missing_ok=True)

    def pending_expiry(self) -> list[str]:
        """Accounts still valid, soon to require a re-link."""
        now = datetime.now(timezone.utc)
        out = []
        for path in self._dir.glob("*.json"):
            try:
                record = self.load(self._account_from_path(path))
            except Exception:
                continue
            if record and (record.expires_at - now) < timedelta(hours=1):
                out.append(record.account_key)
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
            raise ValueError("unknown session blob version")
        try:
            nonce = base64.b64decode(blob["nonce"])
            ciphertext = base64.b64decode(blob["data"])
        except Exception as e:
            raise SessionAuthError("malformed session blob") from e
        try:
            plaintext = AESGCM(self._key).decrypt(nonce, ciphertext, AAD)
        except InvalidTag as e:
            raise SessionAuthError("session blob failed authentication (tampered or wrong key)") from e
        return json.loads(plaintext)


def cli_gen_key() -> None:
    """`python -m app.rpa.session_store --gen-key`"""
    print(generate_key())


if __name__ == "__main__":
    import sys

    if "--gen-key" in sys.argv:
        cli_gen_key()
    else:
        raise SystemExit("usage: python -m app.rpa.session_store --gen-key")