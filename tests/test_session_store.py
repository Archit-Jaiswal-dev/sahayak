from datetime import datetime, timedelta, timezone

import pytest

from app.rpa.session_store import (
    EncryptedSessionStore,
    SessionAuthError,
    SessionRecord,
    generate_key,
)


def _record(key: str, expires_in_hours: float = 24.0) -> SessionRecord:
    now = datetime.now(timezone.utc)
    return SessionRecord(
        account_key=key,
        storage_state={"cookies": [{"name": "SESSION", "value": "abc123"}]},
        created_at=now,
        expires_at=now + timedelta(hours=expires_in_hours),
    )


def test_roundtrip(tmp_path):
    store = EncryptedSessionStore(key_b64=generate_key(), data_dir=tmp_path)
    store.save(_record("alice"))
    loaded = store.load("alice")
    assert loaded is not None
    assert loaded.account_key == "alice"
    assert loaded.storage_state["cookies"][0]["value"] == "abc123"


def test_file_is_encrypted_at_rest(tmp_path):
    store = EncryptedSessionStore(key_b64=generate_key(), data_dir=tmp_path)
    store.save(_record("bob"))
    blobs = list(tmp_path.glob("*.json"))
    assert len(blobs) == 1
    raw = blobs[0].read_text()
    assert '"cookies"' not in raw
    assert '"SESSION"' not in raw


def test_expired_record_is_dropped(tmp_path):
    store = EncryptedSessionStore(key_b64=generate_key(), data_dir=tmp_path)
    expired = _record("carol", expires_in_hours=-1)
    blob = store._encrypt(expired.as_dict())
    store._path("carol").write_text(__import__("json").dumps(blob))
    assert store.load("carol") is None
    assert list(tmp_path.glob("*.json")) == []


def test_tampered_ciphertext_never_trusted(tmp_path):
    store = EncryptedSessionStore(key_b64=generate_key(), data_dir=tmp_path)
    store.save(_record("dave"))
    path = next(tmp_path.glob("*.json"))
    blob = __import__("json").loads(path.read_text())
    # Flipping a base64 char in the ciphertext MUST invalidate authentication.
    data = blob["data"]
    flipped = data[:-1] + ("A" if data[-1] != "A" else "B")
    blob["data"] = flipped
    path.write_text(__import__("json").dumps(blob))
    assert store.load("dave") is None  # never honoured


def test_wrong_key_never_trusted(tmp_path):
    store = EncryptedSessionStore(key_b64=generate_key(), data_dir=tmp_path)
    store.save(_record("erin"))
    other = EncryptedSessionStore(key_b64=generate_key(), data_dir=tmp_path)
    assert other.load("erin") is None  # undecryptable -> dropped


def test_refuses_storing_expired(tmp_path):
    store = EncryptedSessionStore(key_b64=generate_key(), data_dir=tmp_path)
    with pytest.raises(ValueError):
        store.save(_record("frank", expires_in_hours=-1))
