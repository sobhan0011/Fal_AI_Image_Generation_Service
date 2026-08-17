from __future__ import annotations

import os
import secrets

from pydantic import ValidationError
from fastapi import APIRouter, Header, HTTPException, Request, status

from ..infrastructure.fal.webhook import FalWebhookBody
from .dependencies import FalWebhookVerifierDep, GenerationServiceDep, SettingsDep
from .schemas import CallbackResponse, GenerateImageRequest, GenerateImageResponse


router = APIRouter(
    prefix="/generate/image",
    tags=["image-generation"],
)


@router.post(
    "",
    response_model=GenerateImageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_image(
    body: GenerateImageRequest,
    service: GenerationServiceDep,
    x_demo_key: str | None = Header(default=None),
) -> GenerateImageResponse:
    expected_key = os.getenv("DEMO_KEY")

    if (
        not expected_key
        or not x_demo_key
        or not secrets.compare_digest(x_demo_key, expected_key)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid demo key",
        )

    job = await service.generate(
        user_id=body.user_id,
        prompt=body.prompt,
        aspect_ratio=body.aspect_ratio,
    )

    return GenerateImageResponse(
        request_id=job.request_id,
        status=job.status,
        cost=job.cost,
    )


@router.post(
    "/callback",
    response_model=CallbackResponse,
)
async def image_callback(
    request: Request,
    settings: SettingsDep,
    verifier: FalWebhookVerifierDep,
    service: GenerationServiceDep,
) -> CallbackResponse:
    raw_body = await request.body()

    if settings.fal_verify_webhook_signatures:
        try:
            verified = await verifier.verify(headers=request.headers, body=raw_body)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Webhook verification unavailable",
            ) from exc

        if not verified:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid fal webhook signature",
            )

    try:
        webhook = FalWebhookBody.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid fal webhook body",
        ) from exc

    header_request_id = request.headers.get("x-fal-webhook-request-id")
    if settings.fal_verify_webhook_signatures and header_request_id != webhook.request_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook request_id mismatch",
        )

    result = await service.process_callback(webhook.to_application_callback())

    return CallbackResponse(
        message=result.message,
        request_id=result.request_id,
        status=result.status,
        refunded=result.refunded,
    )