"""Pluggable, encrypted persistence for the MSAL serialized token cache.

Microsoft Graph auth (``notify.providers.office365.credential``) keeps its
token cache as a single serialized MSAL blob per ``tenant:client:flow`` key.
This module implements the async storage backends for that blob — in-memory
(default), file, and Redis — with mandatory Fernet encryption for the
persistent backends unless the caller explicitly opts into plaintext.

No secret (cipher key, serialized cache contents, or token value) is ever
logged.
"""

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union

from cryptography.fernet import Fernet, InvalidToken
from navconfig.logging import logging
from redis import asyncio as aioredis

from notify.exceptions import NotifyAuthError
from notify.conf import (
    NOTIFY_REDIS,
    O365_TOKEN_STORE,
    O365_TOKEN_STORE_DIR,
    O365_TOKEN_STORE_REDIS,
    O365_TOKEN_STORE_TTL,
    O365_TOKEN_CIPHER_KEY,
    O365_TOKEN_ALLOW_UNENCRYPTED,
)

logger = logging.getLogger(__name__)


class TokenCipher:
    """Fernet encryption for serialized token caches."""

    def __init__(self, key: Union[str, bytes]) -> None:
        """Build a Fernet cipher from a urlsafe base64-encoded key.

        Args:
            key: A Fernet key (urlsafe base64, 32 bytes decoded), as a
                `str` or `bytes`.

        Raises:
            NotifyAuthError: If the key is not a valid Fernet key.
        """
        if isinstance(key, str):
            key = key.encode("utf-8")
        try:
            self._fernet = Fernet(key)
        except (ValueError, TypeError) as exc:
            raise NotifyAuthError(
                "Invalid O365 token cipher key: must be a urlsafe base64-encoded 32-byte Fernet key."
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext into a Fernet token (urlsafe base64 string)."""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, token: str) -> str:
        """Decrypt a Fernet token back into plaintext.

        Raises:
            NotifyAuthError: When the ciphertext is invalid, corrupt, or was
                encrypted with a different key.
        """
        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError) as exc:
            raise NotifyAuthError(
                "Unable to decrypt O365 token cache: invalid ciphertext or wrong cipher key."
            ) from exc


class TokenStore(ABC):
    """Async persistence for one serialized MSAL token cache per key."""

    @abstractmethod
    async def load(self, key: str) -> Optional[str]:
        """Return the plaintext serialized cache, or None if absent or unreadable."""

    @abstractmethod
    async def save(self, key: str, value: str) -> None:
        """Persist the plaintext serialized cache under `key`."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove the persisted cache for `key`, if any."""

    async def close(self) -> None:
        """Release connections; default no-op."""
        return None


class MemoryTokenStore(TokenStore):
    """In-process, unencrypted token store (the default)."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def load(self, key: str) -> Optional[str]:
        return self._data.get(key)

    async def save(self, key: str, value: str) -> None:
        self._data[key] = value

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)


class FileTokenStore(TokenStore):
    """File-backed token store; encrypted unless `allow_unencrypted=True`."""

    def __init__(
        self,
        directory: Union[str, Path],
        *,
        cipher_key: Optional[str] = None,
        allow_unencrypted: bool = False,
    ) -> None:
        """Build a file-backed store rooted at `directory`.

        Raises:
            NotifyAuthError: If no cipher key is given and `allow_unencrypted`
                is not explicitly True.
        """
        if not cipher_key and not allow_unencrypted:
            raise NotifyAuthError(
                "O365 file token store requires O365_TOKEN_CIPHER_KEY, or explicit allow_unencrypted=True."
            )
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._cipher = TokenCipher(cipher_key) if cipher_key else None

    def _path_for(self, key: str) -> Path:
        # Keys carry ':' (tenant:client:flow); make them filesystem-safe.
        safe_name = key.replace(":", "_").replace("/", "_")
        return self._directory.joinpath(f"{safe_name}.token")

    async def load(self, key: str) -> Optional[str]:
        import aiofiles

        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            async with aiofiles.open(path, mode="r", encoding="utf-8") as fh:
                raw = await fh.read()
        except OSError:
            return None
        if self._cipher is not None:
            try:
                return self._cipher.decrypt(raw)
            except NotifyAuthError:
                logger.warning("Discarding unreadable O365 token cache file for key=%s", key)
                await self.delete(key)
                return None
        return raw

    async def save(self, key: str, value: str) -> None:
        import aiofiles

        path = self._path_for(key)
        payload = self._cipher.encrypt(value) if self._cipher is not None else value
        async with aiofiles.open(path, mode="w", encoding="utf-8") as fh:
            await fh.write(payload)
        os.chmod(path, 0o600)

    async def delete(self, key: str) -> None:
        path = self._path_for(key)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


class RedisTokenStore(TokenStore):
    """Redis-backed token store; encrypted unless `allow_unencrypted=True`.

    Falls back to an in-memory copy for the rest of the process when Redis
    is unreachable; never blocks or raises out of `load`/`save`/`delete`
    because of a Redis connection failure.
    """

    def __init__(
        self,
        url: str,
        *,
        cipher_key: Optional[str] = None,
        allow_unencrypted: bool = False,
        prefix: str = "notify:o365:token:",
        ttl: Optional[int] = None,
    ) -> None:
        """Build a Redis-backed store.

        Raises:
            NotifyAuthError: If no cipher key is given and `allow_unencrypted`
                is not explicitly True.
        """
        if not cipher_key and not allow_unencrypted:
            raise NotifyAuthError(
                "O365 Redis token store requires O365_TOKEN_CIPHER_KEY, or explicit allow_unencrypted=True."
            )
        self._url = url
        self._prefix = prefix
        self._ttl = ttl or None
        self._cipher = TokenCipher(cipher_key) if cipher_key else None
        self._redis: Optional[aioredis.Redis] = None
        self._fallback = MemoryTokenStore()
        self._redis_broken = False

    def _redis_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def _get_redis(self) -> Optional["aioredis.Redis"]:
        if self._redis_broken:
            return None
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(self._url, decode_responses=True)
            except Exception as exc:  # noqa: BLE001 - any connection setup failure
                logger.warning("O365 Redis token store unavailable, falling back to memory: %s", exc)
                self._redis_broken = True
                return None
        return self._redis

    async def load(self, key: str) -> Optional[str]:
        redis = await self._get_redis()
        if redis is None:
            return await self._fallback.load(key)
        try:
            raw = await redis.get(self._redis_key(key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("O365 Redis token store read failed, falling back to memory: %s", exc)
            self._redis_broken = True
            return await self._fallback.load(key)
        if raw is None:
            return None
        if self._cipher is not None:
            try:
                return self._cipher.decrypt(raw)
            except NotifyAuthError:
                logger.warning("Discarding unreadable O365 token cache in Redis for key=%s", key)
                await self.delete(key)
                return None
        return raw

    async def save(self, key: str, value: str) -> None:
        redis = await self._get_redis()
        if redis is None:
            await self._fallback.save(key, value)
            return
        payload = self._cipher.encrypt(value) if self._cipher is not None else value
        try:
            if self._ttl:
                await redis.set(self._redis_key(key), payload, ex=self._ttl)
            else:
                await redis.set(self._redis_key(key), payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("O365 Redis token store write failed, falling back to memory: %s", exc)
            self._redis_broken = True
            await self._fallback.save(key, value)

    async def delete(self, key: str) -> None:
        redis = await self._get_redis()
        if redis is None:
            await self._fallback.delete(key)
            return
        try:
            await redis.delete(self._redis_key(key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("O365 Redis token store delete failed, falling back to memory: %s", exc)
            self._redis_broken = True
            await self._fallback.delete(key)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


def build_token_store(kind: Optional[Union[str, TokenStore]] = None) -> TokenStore:
    """Resolve "memory" | "file" | "redis" | instance | None (→ O365_TOKEN_STORE, default "memory")
    using notify.conf settings.

    Args:
        kind: A `TokenStore` instance (returned as-is), one of the string
            kinds, or `None` to use the `O365_TOKEN_STORE` setting.

    Returns:
        TokenStore: The resolved store instance.

    Raises:
        NotifyAuthError: For an unknown kind, or when a persistent store is
            requested without a cipher key and without `allow_unencrypted`.
    """
    if isinstance(kind, TokenStore):
        return kind
    resolved = kind or O365_TOKEN_STORE or "memory"
    if resolved == "memory":
        return MemoryTokenStore()
    if resolved == "file":
        return FileTokenStore(
            O365_TOKEN_STORE_DIR,
            cipher_key=O365_TOKEN_CIPHER_KEY,
            allow_unencrypted=O365_TOKEN_ALLOW_UNENCRYPTED,
        )
    if resolved == "redis":
        return RedisTokenStore(
            O365_TOKEN_STORE_REDIS or NOTIFY_REDIS,
            cipher_key=O365_TOKEN_CIPHER_KEY,
            allow_unencrypted=O365_TOKEN_ALLOW_UNENCRYPTED,
            ttl=O365_TOKEN_STORE_TTL or None,
        )
    raise NotifyAuthError(f"Unknown O365 token store kind: {resolved!r} (expected memory, file, or redis).")
