from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.helpers import (
    create_generation,
    get_files,
    send_failure_callback,
    send_success_callback,
)


@pytest.mark.asyncio
async def test_successful_generation_appears_in_files(
    client: AsyncClient,
):
    generation = await create_generation(client)

    await send_success_callback(
        client,
        generation["request_id"],
    )

    data = await get_files(client)

    assert len(data["jobs"]) == 1

    job = data["jobs"][0]

    assert job["request_id"] == generation["request_id"]
    assert job["status"] == "SUCCESS"
    assert job["request_url"] == "https://example.com/image.png"


@pytest.mark.asyncio
async def test_failed_job_appears_in_files(
    client: AsyncClient,
):
    generation = await create_generation(client)

    await send_failure_callback(
        client,
        generation["request_id"],
    )

    data = await get_files(client)

    assert len(data["jobs"]) == 1

    job = data["jobs"][0]

    assert job["request_id"] == generation["request_id"]
    assert job["status"] == "FAILED"
    assert job["is_refunded"] is True


@pytest.mark.asyncio
async def test_queued_job_appears_in_files(
    client: AsyncClient,
):
    generation = await create_generation(client)

    data = await get_files(client)

    assert len(data["jobs"]) == 1

    job = data["jobs"][0]

    assert job["request_id"] == generation["request_id"]
    assert job["status"] == "IN_QUEUE"
    assert job["request_url"] is None


@pytest.mark.asyncio
async def test_files_returns_all_generation_statuses(
    client: AsyncClient,
):
    success_job = await create_generation(client)
    failed_job = await create_generation(client)
    queued_job = await create_generation(client)

    await send_success_callback(
        client,
        success_job["request_id"],
    )

    await send_failure_callback(
        client,
        failed_job["request_id"],
    )

    data = await get_files(client)

    assert len(data["jobs"]) == 3

    jobs = {
        job["request_id"]: job
        for job in data["jobs"]
    }

    assert jobs[success_job["request_id"]]["status"] == "SUCCESS"
    assert jobs[failed_job["request_id"]]["status"] == "FAILED"
    assert jobs[queued_job["request_id"]]["status"] == "IN_QUEUE"


@pytest.mark.asyncio
async def test_successful_file_contains_image_url(
    client: AsyncClient,
):
    generation = await create_generation(client)

    await send_success_callback(
        client,
        generation["request_id"],
        image_url="https://example.com/final-image.png",
    )

    data = await get_files(client)

    job = data["jobs"][0]

    assert job["request_url"] == "https://example.com/final-image.png"