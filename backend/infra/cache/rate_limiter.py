from app.core.config import settings


class RateLimiter:
    def __init__(self, rpm: int | None = None):
        self._rpm = rpm or settings.rate_limit_rpm_default

    async def allow(self, key: str) -> bool:
        # Placeholder; implement Redis sliding window
        return True
