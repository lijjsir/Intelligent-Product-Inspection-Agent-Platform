from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class VisionDetectorClient:
    def __init__(self) -> None:
        self._url = settings.vision_detector_url.strip()
        self._api_key = settings.vision_detector_api_key.strip()
        self._timeout = settings.vision_detector_timeout_sec

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    async def detect(
        self,
        *,
        image_urls: list[str],
        product_id: str | None = None,
        spec_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled or not image_urls:
            return None

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "image_urls": image_urls,
            "product_id": product_id,
            "spec_id": spec_id,
        }

        async with httpx.AsyncClient(timeout=float(self._timeout)) as client:
            response = await client.post(self._url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        return data if isinstance(data, dict) else None
