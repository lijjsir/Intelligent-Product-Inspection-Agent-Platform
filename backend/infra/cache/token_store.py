class TokenStore:
    async def is_revoked(self, token: str) -> bool:
        return False

    async def revoke(self, token: str, ttl_seconds: int) -> None:
        return None
