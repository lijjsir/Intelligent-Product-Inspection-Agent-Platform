from app.core.config import settings


class S3Client:
    def __init__(self):
        self._endpoint = settings.s3_endpoint

    async def upload(self, key: str, data: bytes) -> str:
        return f"{self._endpoint}/{settings.s3_bucket}/{key}"
