from __future__ import annotations


import time
import base64
import asyncio
import hashlib
from typing import Any, Literal
from dataclasses import dataclass

import httpx
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
from pydantic import BaseModel, Field, HttpUrl

from ...models import FalCallback


class FalImage(BaseModel):
    url: HttpUrl
    content_type: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    width: int | None = None
    height: int | None = None


class FalSuccessPayload(BaseModel):
    images: list[FalImage] = Field(default_factory=list)
    description: str | None = None


class FalWebhookBody(BaseModel):
    request_id: str
    gateway_request_id: str | None = None
    status: Literal["OK", "ERROR"]
    payload: dict[str, Any] | None = None
    error: str | None = None
    payload_error: str | None = None

    def to_application_callback(self) -> FalCallback:
        if self.status == "ERROR":
            return FalCallback(
                request_id=self.request_id,
                status="ERROR",
                error=self.error or "fal.ai generation failed",
            )

        if self.payload_error:
            return FalCallback(
                request_id=self.request_id,
                status="ERROR",
                error=self.payload_error,
            )

        try:
            payload = FalSuccessPayload.model_validate(self.payload or {})
        except Exception:
            return FalCallback(
                request_id=self.request_id,
                status="ERROR",
                error="fal.ai returned an invalid success payload",
            )

        if not payload.images:
            return FalCallback(
                request_id=self.request_id,
                status="ERROR",
                error="fal.ai returned success without an image",
            )

        return FalCallback(
            request_id=self.request_id,
            status="OK",
            image_url=str(payload.images[0].url),
        )


@dataclass(slots=True)
class _CachedJwks:
    keys: list[dict]
    fetched_at: float


class FalWebhookVerifier:
    """Verify fal webhook signatures according to fal's ED25519 webhook spec."""
    def __init__(
        self,
        *,
        jwks_url: str,
        timestamp_tolerance_seconds: int = 300,
        cache_seconds: int = 24 * 60 * 60,
    ) -> None:
        self.jwks_url = jwks_url
        self.timestamp_tolerance_seconds = timestamp_tolerance_seconds
        self.cache_seconds = cache_seconds
        self._cache: _CachedJwks | None = None
        self._lock = asyncio.Lock()

    async def verify(self, *, headers, body: bytes) -> bool:
        request_id = headers.get("x-fal-webhook-request-id")
        user_id = headers.get("x-fal-webhook-user-id")
        timestamp = headers.get("x-fal-webhook-timestamp")
        signature_hex = headers.get("x-fal-webhook-signature")

        if not all((request_id, user_id, timestamp, signature_hex)):
            return False

        try:
            timestamp_int = int(timestamp)
        except ValueError:
            return False

        if abs(int(time.time()) - timestamp_int) > self.timestamp_tolerance_seconds:
            return False

        body_hash = hashlib.sha256(body).hexdigest()
        message = "\n".join((request_id, user_id, timestamp, body_hash)).encode("utf-8")

        try:
            signature = bytes.fromhex(signature_hex)
        except ValueError:
            return False

        for key_info in await self._get_keys():
            encoded_key = key_info.get("x")
            if not isinstance(encoded_key, str):
                continue

            try:
                padding = "=" * (-len(encoded_key) % 4)
                public_key = base64.urlsafe_b64decode(encoded_key + padding)
                VerifyKey(public_key).verify(message, signature)
                return True
            except (BadSignatureError, ValueError, TypeError):
                continue

        return False

    async def _get_keys(self) -> list[dict]:
        now = time.time()
        if self._cache and now - self._cache.fetched_at < self.cache_seconds:
            return self._cache.keys

        async with self._lock:
            now = time.time()
            if self._cache and now - self._cache.fetched_at < self.cache_seconds:
                return self._cache.keys

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.jwks_url)
                response.raise_for_status()
                keys = response.json().get("keys", [])

            self._cache = _CachedJwks(keys=keys, fetched_at=now)
            return keys
