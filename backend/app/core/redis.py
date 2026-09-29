import redis.asyncio as redis

from app.core.config import settings

# One pooled client per process, shared by streaks, rate limiting, etc.
redis_client = redis.from_url(settings.redis_url)