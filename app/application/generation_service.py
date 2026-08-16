from __future__ import annotations


from uuid import UUID
from decimal import Decimal

from ..errors import FalSubmissionError
from .ports import FalGateway, GenerationUnitOfWorkFactory
from ..models import CallbackResult, FalCallback, GenerationJobData, UserJobsData


class GenerationService:
    def __init__(
        self,
        *,
        unit_of_work_factory: GenerationUnitOfWorkFactory,
        fal_gateway: FalGateway,
        webhook_url: str,
        generation_cost: Decimal,
    ) -> None:
        self.unit_of_work_factory = unit_of_work_factory
        self.fal_gateway = fal_gateway
        self.webhook_url = webhook_url
        self.generation_cost = generation_cost

    async def generate(
        self,
        *,
        user_id: UUID,
        prompt: str,
        aspect_ratio: str,
    ) -> GenerationJobData:
        async with self.unit_of_work_factory() as uow:
            await uow.debit_user(user_id=user_id, amount=self.generation_cost)

            try:
                request_id = await self.fal_gateway.submit_image(
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                    webhook_url=self.webhook_url,
                )
            except Exception as exc:
                raise FalSubmissionError(
                    "fal.ai rejected or failed to queue the request"
                ) from exc

            return await uow.create_job(
                request_id=request_id,
                user_id=user_id,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                cost=self.generation_cost,
            )

    async def process_callback(self, callback: FalCallback) -> CallbackResult:
        async with self.unit_of_work_factory() as uow:
            if callback.status == "OK" and callback.image_url is not None:
                processed = await uow.mark_success(
                    request_id=callback.request_id,
                    image_url=callback.image_url,
                )
            else:
                processed = await uow.mark_failed_and_refund(
                    request_id=callback.request_id,
                    error_message=callback.error or "fal.ai generation failed",
                )

            if processed is not None:
                return processed

            return await uow.get_callback_state(callback.request_id)

    async def get_user_jobs(self, user_id: UUID) -> UserJobsData:
        async with self.unit_of_work_factory() as uow:
            return await uow.get_user_jobs(user_id)
