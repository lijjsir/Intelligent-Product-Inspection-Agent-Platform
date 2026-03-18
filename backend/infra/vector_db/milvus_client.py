from app.core.config import settings


class MilvusClient:
    def __init__(self):
        self._host = settings.vector_db_host
        self._port = settings.vector_db_port

    async def search(self, collection: str, vector: list[float], top_k: int = 5):
        return []
