from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.conftest import MISSING_USER_ID, USER_ID
from tests.fakes import FakeFalGateway
from tests.helpers import create_generation, get_files


@pytest.mark.asyncio
async def test_generation_creates_queued_job(
    client: AsyncClient,
):
    data = await create_generation(client)

    assert data["request_id"] == "fal-request-1"
    assert data["status"] == "IN_QUEUE"
    assert Decimal(str(data["cost"])) == Decimal("50.00")


@pytest.mark.asyncio
async def test_generation_deducts_balance(
    client: AsyncClient,
):
    await create_generation(client)

    data = await get_files(client)

    assert Decimal(str(data["ai_balance"])) == Decimal("950.00")


@pytest.mark.asyncio
async def test_nonexistent_user_cannot_generate(
    client: AsyncClient,
):
    response = await client.post(
        "/generate/image",
        json={
            "user_id": str(MISSING_USER_ID),
            "prompt": "test",
            "aspect_ratio": "1:1",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_insufficient_balance(
    client: AsyncClient,
):
    for _ in range(20):
        await create_generation(client)

    data = await get_files(client)

    assert Decimal(str(data["ai_balance"])) == Decimal("0.00")

    response = await client.post(
        "/generate/image",
        json={
            "user_id": str(USER_ID),
            "prompt": "one more image",
            "aspect_ratio": "1:1",
        },
    )

    assert response.status_code == 400

    data = await get_files(client)

    assert Decimal(str(data["ai_balance"])) == Decimal("0.00")


@pytest.mark.asyncio
async def test_fal_submission_failure_rolls_back_balance(
    client: AsyncClient,
    fake_fal: FakeFalGateway,
):
    fake_fal.should_fail = True

    response = await client.post(
        "/generate/image",
        json={
            "user_id": str(USER_ID),
            "prompt": "this will fail",
            "aspect_ratio": "1:1",
        },
    )

    assert response.status_code >= 400

    data = await get_files(client)

    # Debit must have rolled back.
    assert Decimal(str(data["ai_balance"])) == Decimal("1000.00")