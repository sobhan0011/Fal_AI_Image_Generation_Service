from __future__ import annotations

from itertools import count


class FakeFalGateway:
    def __init__(self) -> None:
        self._counter = count(1)
        self.should_fail = False

    async def submit_image(
        self,
        *,
        prompt: str,
        aspect_ratio: str,
        webhook_url: str,
    ) -> str:
        if self.should_fail:
            raise RuntimeError("Fal submission failed")

        return f"fal-request-{next(self._counter)}"