from __future__ import annotations

from uuid import UUID
from typing import Literal
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models import GenerationStatus


AspectRatio = Literal[
    "21:9",
    "16:9",
    "3:2",
    "4:3",
    "5:4",
    "1:1",
    "4:5",
    "3:4",
    "2:3",
    "9:16",
]


class GenerateImageRequest(BaseModel):
    user_id: UUID = Field(
        default=UUID("11111111-1111-1111-1111-111111111111")
    )
    prompt: str = Field(min_length=1, max_length=4000)
    aspect_ratio: AspectRatio = "1:1"


class GenerateImageResponse(BaseModel):
    request_id: str
    status: GenerationStatus
    cost: Decimal


class CallbackResponse(BaseModel):
    message: Literal["processed", "already_processed"]
    request_id: str
    status: GenerationStatus
    refunded: bool = False


class GenerationJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str
    prompt: str
    aspect_ratio: str
    status: GenerationStatus
    cost: Decimal
    is_refunded: bool
    request_url: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class MyFilesResponse(BaseModel):
    user_id: UUID
    ai_balance: Decimal
    jobs: list[GenerationJobResponse]
