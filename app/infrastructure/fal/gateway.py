from __future__ import annotations

import fal_client


class FalClientGateway:
    def __init__(self, model: str) -> None:
        self.model = model

    async def submit_image(
        self,
        *,
        prompt: str,
        aspect_ratio: str,
        webhook_url: str,
    ) -> str:
        handler = await fal_client.submit_async(
            self.model,
            arguments={
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "num_images": 1,
                "output_format": "png",
            },
            webhook_url=webhook_url,
        )
        return handler.request_id
