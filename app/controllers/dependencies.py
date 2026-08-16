from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from ..config import Settings
from ..infrastructure.fal.webhook import FalWebhookVerifier
from ..application.generation_service import GenerationService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_generation_service(request: Request) -> GenerationService:
    return request.app.state.generation_service


def get_fal_webhook_verifier(request: Request) -> FalWebhookVerifier:
    return request.app.state.fal_webhook_verifier


SettingsDep = Annotated[Settings, Depends(get_settings)]
GenerationServiceDep = Annotated[GenerationService, Depends(get_generation_service)]
FalWebhookVerifierDep = Annotated[FalWebhookVerifier, Depends(get_fal_webhook_verifier)]
