from __future__ import annotations

from decimal import Decimal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "fal-image-generation-api"

    database_url: str = "sqlite+aiosqlite:///./app.db"

    fal_model: str = "fal-ai/nano-banana"
    fal_webhook_url: str = "http://localhost:8000/generate/image/callback"
    fal_verify_webhook_signatures: bool = True
    fal_jwks_url: str = "https://rest.fal.ai/.well-known/jwks.json"
    fal_webhook_timestamp_tolerance_seconds: int = 300

    image_generation_cost: Decimal = Field(default=Decimal("50.00"), gt=0)
    seed_demo_users: bool = True
    demo_user_balance: Decimal = Field(default=Decimal("1000.00"), ge=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
