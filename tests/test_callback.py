from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.helpers import (
    create_generation,
    get_files,
    send_failure_callback,
    send_success_callback,
)


@pytest.mark.asyncio
async def test_success_callback(
    client: AsyncClient,
):
    generation = await create_generation(client)
    request_id = generation["request_id"]

    response = await send_success_callback(
        client,
        request_id,
    )

    assert response.status_code == 200

    data = await get_files(client)

    job = next(
        job
        for job in data["jobs"]
        if job["request_id"] == request_id
    )

    assert job["status"] == "SUCCESS"
    assert job["request_url"] == "https://example.com/image.png"
    assert job["is_refunded"] is False

    assert Decimal(str(data["ai_balance"])) == Decimal("950.00")


@pytest.mark.asyncio
async def test_failure_callback_refunds_balance(
    client: AsyncClient,
):
    generation = await create_generation(client)
    request_id = generation["request_id"]

    response = await send_failure_callback(
        client,
        request_id,
    )

    assert response.status_code == 200

    data = await get_files(client)

    job = next(
        job
        for job in data["jobs"]
        if job["request_id"] == request_id
    )

    assert job["status"] == "FAILED"
    assert job["is_refunded"] is True

    assert Decimal(str(data["ai_balance"])) == Decimal("1000.00")


@pytest.mark.asyncio
async def test_duplicate_failure_refunds_once(
    client: AsyncClient,
):
    generation = await create_generation(client)
    request_id = generation["request_id"]

    first = await send_failure_callback(
        client,
        request_id,
    )

    second = await send_failure_callback(
        client,
        request_id,
    )

    assert first.status_code == 200
    assert second.status_code == 200

    data = await get_files(client)

    # Must not become 1050.
    assert Decimal(str(data["ai_balance"])) == Decimal("1000.00")


@pytest.mark.asyncio
async def test_concurrent_duplicate_failure_refunds_once(
    client: AsyncClient,
):
    generation = await create_generation(client)
    request_id = generation["request_id"]

    response_1, response_2 = await asyncio.gather(
        send_failure_callback(client, request_id),
        send_failure_callback(client, request_id),
    )

    assert response_1.status_code == 200
    assert response_2.status_code == 200

    data = await get_files(client)

    assert Decimal(str(data["ai_balance"])) == Decimal("1000.00")


@pytest.mark.asyncio
async def test_two_different_failures_both_refund(
    client: AsyncClient,
):
    generation_1 = await create_generation(client)
    generation_2 = await create_generation(client)

    before = await get_files(client)

    assert Decimal(str(before["ai_balance"])) == Decimal("900.00")

    await asyncio.gather(
        send_failure_callback(
            client,
            generation_1["request_id"],
        ),
        send_failure_callback(
            client,
            generation_2["request_id"],
        ),
    )

    after = await get_files(client)

    assert Decimal(str(after["ai_balance"])) == Decimal("1000.00")


@pytest.mark.asyncio
async def test_failure_after_success_does_nothing(
    client: AsyncClient,
):
    generation = await create_generation(client)
    request_id = generation["request_id"]

    await send_success_callback(
        client,
        request_id,
    )

    await send_failure_callback(
        client,
        request_id,
    )

    data = await get_files(client)

    job = next(
        job
        for job in data["jobs"]
        if job["request_id"] == request_id
    )

    assert job["status"] == "SUCCESS"
    assert job["is_refunded"] is False
    assert Decimal(str(data["ai_balance"])) == Decimal("950.00")


@pytest.mark.asyncio
async def test_success_after_failure_does_nothing(
    client: AsyncClient,
):
    generation = await create_generation(client)
    request_id = generation["request_id"]

    await send_failure_callback(
        client,
        request_id,
    )

    await send_success_callback(
        client,
        request_id,
    )

    data = await get_files(client)

    job = next(
        job
        for job in data["jobs"]
        if job["request_id"] == request_id
    )

    assert job["status"] == "FAILED"
    assert job["is_refunded"] is True
    assert job["request_url"] is None

    assert Decimal(str(data["ai_balance"])) == Decimal("1000.00")