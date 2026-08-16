from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import USER_ID


async def create_generation(
    client: AsyncClient,
    *,
    prompt: str = "a futuristic city",
    aspect_ratio: str = "1:1",
) -> dict:
    response = await client.post(
        "/generate/image",
        json={
            "user_id": str(USER_ID),
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
        },
    )

    assert response.status_code in (200, 201, 202)

    return response.json()


async def send_success_callback(
    client: AsyncClient,
    request_id: str,
    *,
    image_url: str = "https://example.com/image.png",
):
    return await client.post(
        "/generate/image/callback",
        json={
            "request_id": request_id,
            "status": "OK",
            "payload": {
                "images": [
                    {
                        "url": image_url,
                    }
                ]
            },
        },
    )


async def send_failure_callback(
    client: AsyncClient,
    request_id: str,
):
    return await client.post(
        "/generate/image/callback",
        json={
            "request_id": request_id,
            "status": "ERROR",
            "error": "generation failed",
            "payload": None,
        },
    )


async def get_files(
    client: AsyncClient,
    user_id=USER_ID,
) -> dict:
    response = await client.get(
        f"/my-files/{user_id}"
    )

    assert response.status_code == 200

    return response.json()