from app.core.config import settings


def get_client():
    # Placeholder; integrate aioredis in production
    return {"url": settings.redis_url}
