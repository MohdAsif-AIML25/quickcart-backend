import logging

from fastapi import APIRouter, Response
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import DbSession
from app.core.config import get_settings
from app.core.redis_client import redis_client
from app.schemas.health import HealthResponse, ReadinessResponse

logger = logging.getLogger("quickcart.health")

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse, summary="Liveness: is the process running?")
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        app=settings.app_name, version=settings.app_version, environment=settings.environment
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness: can we serve traffic?",
    responses={503: {"description": "Database is unreachable"}},
)
def readiness(db: DbSession, response: Response) -> ReadinessResponse:
    try:
        db.execute(text("SELECT 1"))
        database = "up"
    except SQLAlchemyError:
        logger.warning("readiness_database_down")
        database = "down"

    try:
        redis_client.ping()
        redis = "up"
    except RedisError:
        logger.warning("readiness_redis_down")
        redis = "down"

    # Redis is optional (cache + rate limit degrade gracefully); PostgreSQL is not.
    ready = database == "up"
    if not ready:
        response.status_code = 503
    return ReadinessResponse(
        status="ready" if ready else "not_ready", database=database, redis=redis
    )
