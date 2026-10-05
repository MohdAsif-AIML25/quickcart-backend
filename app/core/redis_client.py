import redis

from app.core.config import get_settings

redis_client: redis.Redis= redis.Redis.from_url(
    get_settings().redis_url,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
)
