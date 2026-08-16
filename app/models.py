from __future__ import annotations

import enum
from uuid import UUID
from typing import Literal
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass


class GenerationStatus(str, enum.Enum):
    IN_QUEUE = "IN_QUEUE"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class GenerationJobData:
    request_id: str
    user_id: UUID
    prompt: str
    aspect_ratio: str
    status: GenerationStatus
    cost: Decimal
    is_refunded: bool
    request_url: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class UserJobsData:
    user_id: UUID
    ai_balance: Decimal
    jobs: list[GenerationJobData]


@dataclass(frozen=True, slots=True)
class FalCallback:
    request_id: str
    status: Literal["OK", "ERROR"]
    image_url: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CallbackResult:
    message: Literal["processed", "already_processed"]
    request_id: str
    status: GenerationStatus
    refunded: bool = False
