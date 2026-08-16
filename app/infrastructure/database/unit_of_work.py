from __future__ import annotations

from uuid import UUID
from typing import cast
from decimal import Decimal
from types import TracebackType
from sqlalchemy.engine import CursorResult

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...errors import (
    UserNotFoundError,
    InsufficientBalanceError,
    GenerationJobNotFoundError,
)
from ...models import (
    UserJobsData,
    CallbackResult,
    GenerationJobData,
    GenerationStatus,
)
from .models import GenerationJob, User


class SqlAlchemyGenerationUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._transaction = None

    async def __aenter__(self) -> "SqlAlchemyGenerationUnitOfWork":
        self._session = self._session_factory()
        self._transaction = self._session.begin()
        await self._transaction.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._transaction is None or self._session is None:
            return

        try:
            await self._transaction.__aexit__(exc_type, exc, tb)
        finally:
            await self._session.close()
            self._transaction = None
            self._session = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Unit of work must be used inside 'async with'")
        return self._session

    async def debit_user(self, *, user_id: UUID, amount: Decimal) -> None:
        debit = await self.session.execute(
            update(User)
            .where(
                User.id == user_id,
                User.ai_balance >= amount,
            )
            .values(ai_balance=User.ai_balance - amount)
        )

        result = cast(CursorResult, debit)

        if result.rowcount == 1:
            return

        user_exists = await self.session.scalar(select(User.id).where(User.id == user_id))
        if user_exists is None:
            raise UserNotFoundError(f"User {user_id} does not exist")

        raise InsufficientBalanceError("Insufficient AI balance")

    async def create_job(
        self,
        *,
        request_id: str,
        user_id: UUID,
        prompt: str,
        aspect_ratio: str,
        cost: Decimal,
    ) -> GenerationJobData:
        job = GenerationJob(
            request_id=request_id,
            user_id=user_id,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            status=GenerationStatus.IN_QUEUE,
            cost=cost,
            is_refunded=False,
        )
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return self._to_job_data(job)

    async def mark_success(
        self,
        *,
        request_id: str,
        image_url: str,
    ) -> CallbackResult | None:
        result = await self.session.execute(
            update(GenerationJob)
            .where(
                GenerationJob.request_id == request_id,
                GenerationJob.status == GenerationStatus.IN_QUEUE,
            )
            .values(
                status=GenerationStatus.SUCCESS,
                request_url=image_url,
                error_message=None,
            )
            .returning(
                GenerationJob.request_id,
                GenerationJob.status,
                GenerationJob.is_refunded,
            )
        )
        claimed = result.first()
        if claimed is None:
            return None

        return CallbackResult(
            message="processed",
            request_id=claimed.request_id,
            status=claimed.status,
            refunded=False,
        )

    async def mark_failed_and_refund(
        self,
        *,
        request_id: str,
        error_message: str,
    ) -> CallbackResult | None:
        result = await self.session.execute(
            update(GenerationJob)
            .where(
                GenerationJob.request_id == request_id,
                GenerationJob.status == GenerationStatus.IN_QUEUE,
                GenerationJob.is_refunded.is_(False),
            )
            .values(
                status=GenerationStatus.FAILED,
                is_refunded=True,
                error_message=error_message,
            )
            .returning(
                GenerationJob.request_id,
                GenerationJob.user_id,
                GenerationJob.cost,
                GenerationJob.status,
            )
        )
        claimed = result.first()
        if claimed is None:
            return None

        wallet = await self.session.execute(
            update(User)
            .where(User.id == claimed.user_id)
            .values(ai_balance=User.ai_balance + claimed.cost)
        )

        result = cast(CursorResult, wallet)

        if result.rowcount != 1:
            raise UserNotFoundError(
                f"User {claimed.user_id} for generation job no longer exists"
            )

        return CallbackResult(
            message="processed",
            request_id=claimed.request_id,
            status=claimed.status,
            refunded=True,
        )

    async def get_callback_state(self, request_id: str) -> CallbackResult:
        job = await self.session.scalar(
            select(GenerationJob).where(GenerationJob.request_id == request_id)
        )
        if job is None:
            raise GenerationJobNotFoundError(request_id)

        return CallbackResult(
            message="already_processed",
            request_id=job.request_id,
            status=job.status,
            refunded=job.is_refunded,
        )

    async def get_user_jobs(self, user_id: UUID) -> UserJobsData:
        user = await self.session.get(User, user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} does not exist")

        jobs = list(
            (
                await self.session.scalars(
                    select(GenerationJob)
                    .where(GenerationJob.user_id == user_id)
                    .order_by(GenerationJob.created_at.desc(), GenerationJob.id.desc())
                )
            ).all()
        )

        return UserJobsData(
            user_id=user.id,
            ai_balance=user.ai_balance,
            jobs=[self._to_job_data(job) for job in jobs],
        )

    @staticmethod
    def _to_job_data(job: GenerationJob) -> GenerationJobData:
        return GenerationJobData(
            request_id=job.request_id,
            user_id=job.user_id,
            prompt=job.prompt,
            aspect_ratio=job.aspect_ratio,
            status=job.status,
            cost=job.cost,
            is_refunded=job.is_refunded,
            request_url=job.request_url,
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


class SqlAlchemyGenerationUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyGenerationUnitOfWork:
        return SqlAlchemyGenerationUnitOfWork(self._session_factory)
