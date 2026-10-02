import logging 
from collections.abc import Callable 
from fastapi import Request 
from redis.exceptions import RedisError 
from app.core.config import get_settings 
from app.core.exceptions import TooManyRequestsError 
from app.core.redis_client import redis_client 

logger=logging.getLogger("quickcart.rate_limit")

def rate_limiter(scope:str,limit:int,window_seconds:int)-> Callable[[Request], None]:
    """Fixed-window limiter: at most `limit` requests per IP per window."""

    def dependency(request:Request) -> None:
        client_ip=request.client.host if request.client else "unkown"
        key=f"ratelimit":{scope}:{client_ip}"
        try:
            pipe=redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key,window_seconds,nx=True)
            count,_=pipe.execute()
            retry_after=max(redis_client.ttl(key), 1) if count > limit else 0
        except RedisError:
            logger.warning("rate_limit_unavailable",extra={"scope":scope})
            return 

        if count>limit:
            raise TooManyRequestsError(
                f"Too many attempts.Try again in {retry_after} seconds."
                headers={"Retry-After":str(retry_after)},
            )
    return dependency

_settings = get_settings()
login_rate_limiter = rate_limiter(
    "login", _settings.login_rate_limit, _settings.login_rate_window_seconds
)
