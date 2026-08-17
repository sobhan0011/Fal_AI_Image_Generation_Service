from __future__ import annotations

from uuid import UUID
from typing import Annotated

from fastapi import Path
from fastapi import APIRouter

from .dependencies import GenerationServiceDep
from .schemas import GenerationJobResponse, MyFilesResponse


router = APIRouter(tags=["files"])

DemoUserId = Annotated[
    UUID,
    Path(
        examples=["11111111-1111-1111-1111-111111111111"]
    ),
]

@router.get(
    "/my-files/{user_id}",
    response_model=MyFilesResponse,
)
async def my_files(
    user_id: DemoUserId,
    service: GenerationServiceDep,
) -> MyFilesResponse:
    result = await service.get_user_jobs(user_id)

    return MyFilesResponse(
        user_id=result.user_id,
        ai_balance=result.ai_balance,
        jobs=[GenerationJobResponse.model_validate(job) for job in result.jobs],
    )
