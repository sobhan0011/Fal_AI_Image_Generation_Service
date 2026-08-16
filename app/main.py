from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import Settings

from .application.generation_service import GenerationService

from .controllers import api_router
from .controllers.exception_handlers import register_exception_handlers

from .infrastructure.database.database import Database
from .infrastructure.fal.gateway import FalClientGateway
from .infrastructure.fal.webhook import FalWebhookVerifier
from .infrastructure.database.unit_of_work import SqlAlchemyGenerationUnitOfWorkFactory


def create_app() -> FastAPI:
    settings = Settings()

    database = Database(settings.database_url)

    unit_of_work_factory = SqlAlchemyGenerationUnitOfWorkFactory(database.session_factory)
    
    fal_gateway = FalClientGateway(settings.fal_model)

    webhook_verifier = FalWebhookVerifier(
        jwks_url=settings.fal_jwks_url,
        timestamp_tolerance_seconds=settings.fal_webhook_timestamp_tolerance_seconds,
    )

    generation_service = GenerationService(
        unit_of_work_factory=unit_of_work_factory,
        fal_gateway=fal_gateway,
        webhook_url=settings.fal_webhook_url,
        generation_cost=settings.image_generation_cost,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await database.dispose()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = database
    app.state.generation_service = generation_service
    app.state.fal_webhook_verifier = webhook_verifier

    register_exception_handlers(app)
    app.include_router(api_router)

    return app


app = create_app()
