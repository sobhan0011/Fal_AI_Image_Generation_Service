from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from app.infrastructure.database.models import Base, User

from tests.fakes import FakeFalGateway


USER_ID = UUID("11111111-1111-1111-1111-111111111111")
MISSING_USER_ID = UUID("99999999-9999-9999-9999-999999999999")


@pytest.fixture
def fake_fal() -> FakeFalGateway:
    return FakeFalGateway()


@pytest_asyncio.fixture
async def client(tmp_path, fake_fal: FakeFalGateway):
    database_path = tmp_path / "test.db"

    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{database_path}",
        fal_webhook_url="http://test/generate/image/callback",
        fal_verify_webhook_signatures=False,
        image_generation_cost=Decimal("50.00"),
    )

    app = create_app(
        settings=settings,
        fal_gateway=fake_fal,
    )

    database = app.state.database

    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with database.session_factory() as session:
        async with session.begin():
            session.add(
                User(
                    id=USER_ID,
                    ai_balance=Decimal("1000.00"),
                )
            )

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client

    await database.dispose()