from __future__ import annotations

from uuid import UUID
from decimal import Decimal
from typing import Protocol

from ..models import CallbackResult, GenerationJobData, UserJobsData


class FalGateway(Protocol):
    async def submit_image(
        self,
        *,
        prompt: str,
        aspect_ratio: str,
        webhook_url: str,
    ) -> str:
        ...


class GenerationUnitOfWork(Protocol):
    async def __aenter__(self) -> "GenerationUnitOfWork": ...

    async def __aexit__(self, exc_type, exc, tb) -> None: ...

    async def debit_user(self, *, user_id: UUID, amount: Decimal) -> None: ...

    async def create_job(
        self,
        *,
        request_id: str,
        user_id: UUID,
        prompt: str,
        aspect_ratio: str,
        cost: Decimal,
    ) -> GenerationJobData: ...

    async def mark_success(
        self,
        *,
        request_id: str,
        image_url: str,
    ) -> CallbackResult | None: ...

    async def mark_failed_and_refund(
        self,
        *,
        request_id: str,
        error_message: str,
    ) -> CallbackResult | None: ...

    async def get_callback_state(self, request_id: str) -> CallbackResult: ...

    async def get_user_jobs(self, user_id: UUID) -> UserJobsData: ...


class GenerationUnitOfWorkFactory(Protocol):
    def __call__(self) -> GenerationUnitOfWork: ...
