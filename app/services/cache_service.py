import logging

from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.redis_client import redis_client
from app.schemas.product import PaginatedProducts

logger = logging.getLogger("quickcart.cache")

VERSION_KEY = "products:cache_version"


def build_products_key(page: int, limit: int, category: str | None, search: str | None) -> str:
    cat = (category or "").strip().lower()
    term = (search or "").strip().lower()
    return f"p={page}:l={limit}:c={cat}:s={term}"


def _full_key(params_key: str) -> str:
    version = redis_client.get(VERSION_KEY) or "0"
    return f"products:list:v{version}:{params_key}"


def get_cached_products(params_key: str) -> PaginatedProducts | None:
    try:
        raw = redis_client.get(_full_key(params_key))
    except RedisError:
        logger.warning("cache_read_failed")
        return None  # Redis down -> just go to the database
    return PaginatedProducts.model_validate_json(raw) if raw else None


def set_cached_products(params_key: str, value: PaginatedProducts) -> None:
    try:
        redis_client.set(
            _full_key(params_key),
            value.model_dump_json(),
            ex=get_settings().product_cache_ttl_seconds,
        )
    except RedisError:
        logger.warning("cache_write_failed")


def invalidate_product_cache() -> None:
    """Bump the version: every old key becomes unreachable and expires via TTL."""
    try:
        redis_client.incr(VERSION_KEY)
    except RedisError:
        logger.warning("cache_invalidate_failed")