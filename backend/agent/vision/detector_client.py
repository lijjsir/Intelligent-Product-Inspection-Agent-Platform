from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class VisionDetectorClient:
    def __init__(self) -> None:
        """读取视觉检测服务配置，准备向外部检测器发送请求。"""
        self._url = settings.vision_detector_url.strip()
        self._api_key = settings.vision_detector_api_key.strip()
        self._timeout = settings.vision_detector_timeout_sec

    @property
    def enabled(self) -> bool:
        """判断当前环境是否启用了专用视觉检测服务。"""
        return bool(self._url)

    async def detect(
        self,
        *,
        image_urls: list[str],
        product_id: str | None = None,
        spec_code: str | None = None,
    ) -> dict[str, Any] | None:
        """调用外部视觉检测服务，返回原始结构化检测结果。"""
        if not self.enabled or not image_urls:
            return None

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "image_urls": image_urls,
            "product_id": product_id,
            "spec_code": spec_code,
        }

        async with httpx.AsyncClient(timeout=float(self._timeout), trust_env=False) as client:
            response = await client.post(self._url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        return data if isinstance(data, dict) else None
