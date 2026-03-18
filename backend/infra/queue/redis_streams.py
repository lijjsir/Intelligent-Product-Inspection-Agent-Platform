class RedisStreams:
    async def xadd(self, topic: str, payload: dict) -> None:
        return None

    async def xreadgroup(self, topic: str, group: str, consumer: str, count: int = 10):
        return []
