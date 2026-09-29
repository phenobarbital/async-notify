"""Offline tests for the Office365 Graph token stores and cipher (FEAT-004, M2)."""

import stat
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

from notify.exceptions import NotifyAuthError
from notify.providers.office365.token_store import (
    FileTokenStore,
    MemoryTokenStore,
    RedisTokenStore,
    TokenCipher,
    build_token_store,
)


@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode()


async def test_memory_store_roundtrip():
    store = MemoryTokenStore()
    assert await store.load("k") is None
    await store.save("k", "cache-blob")
    assert await store.load("k") == "cache-blob"
    await store.delete("k")
    assert await store.load("k") is None


def test_file_store_requires_key_or_opt_in(tmp_path: Path):
    with pytest.raises(NotifyAuthError):
        FileTokenStore(tmp_path)
    # explicit opt-in is fine with no key
    FileTokenStore(tmp_path, allow_unencrypted=True)


async def test_file_store_encrypted_on_disk_and_0600(tmp_path: Path, fernet_key: str):
    store = FileTokenStore(tmp_path, cipher_key=fernet_key)
    await store.save("tenant:client:flow", "super-secret-cache-blob")

    path = store._path_for("tenant:client:flow")
    assert path.exists()
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600

    raw_bytes = path.read_bytes()
    assert b"super-secret-cache-blob" not in raw_bytes

    loaded = await store.load("tenant:client:flow")
    assert loaded == "super-secret-cache-blob"


async def test_store_corrupt_value_is_discarded(tmp_path: Path, fernet_key: str):
    store = FileTokenStore(tmp_path, cipher_key=fernet_key)
    path = store._path_for("k")
    path.write_text("not-a-valid-fernet-token", encoding="utf-8")

    result = await store.load("k")
    assert result is None
    assert not path.exists()


async def test_redis_store_fallback_on_connection_error(fernet_key: str, monkeypatch):
    store = RedisTokenStore("redis://localhost:1", cipher_key=fernet_key)

    broken_redis = MagicMock()
    broken_redis.get = AsyncMock(side_effect=ConnectionError("boom"))
    broken_redis.set = AsyncMock(side_effect=ConnectionError("boom"))

    async def _get_redis():
        return broken_redis

    monkeypatch.setattr(store, "_get_redis", _get_redis)

    await store.save("k", "cache-blob")
    assert store._redis_broken is True
    assert await store.load("k") == "cache-blob"  # served from the in-memory fallback


async def test_redis_store_roundtrip_with_working_client(fernet_key: str, monkeypatch):
    store = RedisTokenStore("redis://localhost:1", cipher_key=fernet_key, ttl=60)

    backing: dict[str, str] = {}

    fake_redis = MagicMock()

    async def _get(key):
        return backing.get(key)

    async def _set(key, value, ex=None):
        backing[key] = value

    async def _delete(key):
        backing.pop(key, None)

    fake_redis.get = AsyncMock(side_effect=_get)
    fake_redis.set = AsyncMock(side_effect=_set)
    fake_redis.delete = AsyncMock(side_effect=_delete)

    async def _get_redis():
        return fake_redis

    monkeypatch.setattr(store, "_get_redis", _get_redis)

    await store.save("tenant:client:flow", "cache-blob")
    stored_key = next(iter(backing))
    assert stored_key == "notify:o365:token:tenant:client:flow"
    assert "cache-blob" not in backing[stored_key]  # encrypted at rest

    assert await store.load("tenant:client:flow") == "cache-blob"
    await store.delete("tenant:client:flow")
    assert backing == {}


def test_build_token_store_variants(tmp_path: Path, fernet_key: str):
    assert isinstance(build_token_store("memory"), MemoryTokenStore)
    assert isinstance(build_token_store(None), MemoryTokenStore)  # default from O365_TOKEN_STORE

    instance = MemoryTokenStore()
    assert build_token_store(instance) is instance

    file_store = build_token_store(FileTokenStore(tmp_path, cipher_key=fernet_key))
    assert isinstance(file_store, FileTokenStore)

    with pytest.raises(NotifyAuthError):
        build_token_store("not-a-real-kind")


def test_token_cipher_roundtrip(fernet_key: str):
    cipher = TokenCipher(fernet_key)
    token = cipher.encrypt("plaintext-value")
    assert token != "plaintext-value"
    assert cipher.decrypt(token) == "plaintext-value"


def test_token_cipher_invalid_key_rejected():
    with pytest.raises(NotifyAuthError):
        TokenCipher("not-a-valid-fernet-key")


def test_token_cipher_wrong_key_raises(fernet_key: str):
    cipher = TokenCipher(fernet_key)
    token = cipher.encrypt("plaintext-value")
    other_cipher = TokenCipher(Fernet.generate_key().decode())
    with pytest.raises(NotifyAuthError):
        other_cipher.decrypt(token)
