from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from dotenv import load_dotenv
load_dotenv()

from .config import Settings

from .application.generation_service import GenerationService

from .controllers import api_router
from .controllers.exception_handlers import register_exception_handlers

from .infrastructure.database.database import Database
from .infrastructure.fal.gateway import FalClientGateway
from .infrastructure.fal.webhook import FalWebhookVerifier
from .infrastructure.database.unit_of_work import SqlAlchemyGenerationUnitOfWorkFactory
from .application.ports import FalGateway

def create_app(
    settings: Settings | None = None,
    fal_gateway: FalGateway | None = None,
) -> FastAPI:
    settings = settings or Settings()

    database = Database(settings.database_url)

    unit_of_work_factory = SqlAlchemyGenerationUnitOfWorkFactory(database.session_factory)
    
    fal_gateway = fal_gateway or FalClientGateway(
        settings.fal_model
    )
    webhook_verifier = FalWebhookVerifier(
        jwks_url=settings.fal_jwks_url,
        timestamp_tolerance_seconds=settings.fal_webhook_timestamp_tolerance_seconds,
    )

    generation_service = GenerationService(
        unit_of_work_factory=unit_of_work_factory,
        fal_gateway=fal_gateway,
        webhook_url=settings.resolved_fal_webhook_url,
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

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/docs")

    app.state.settings = settings
    app.state.database = database
    app.state.generation_service = generation_service
    app.state.fal_webhook_verifier = webhook_verifier

    register_exception_handlers(app)
    app.include_router(api_router)

    return app


app = create_app()
