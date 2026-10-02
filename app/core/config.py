from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration in one typed object, loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env also holds POSTGRES_* values that only docker-compose reads
    )

    # --- Application (Task 1) ---
    app_name: str = "QuickCart API"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"
    log_json: bool = True

    # --- Database (Task 2) ---
    database_url: str = (
        "postgresql+psycopg://quickcart:quickcart_dev_password@localhost:5433/quickcart"
    )

    # --- Auth (Task 3) ---
    jwt_secret_key: str = Field(min_length=32)  # required: app refuses to start without it
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=15, gt=0)
    refresh_token_expire_days: int = Field(default=7, gt=0)

    # --- Redis, caching, rate limiting (Task 8) ---
    redis_url: str = "redis://localhost:6379/0"
    product_cache_ttl_seconds: int = Field(default=60, gt=0)
    login_rate_limit: int = Field(default=5, gt=0)
    login_rate_window_seconds: int = Field(default=60, gt=0)

    # --- Uploads (Task 8) ---
    upload_dir: Path = Path("uploads")
    max_image_size_mb: int = Field(default=2, gt=0)


@lru_cache
def get_settings() -> Settings:
    """Read and validate the environment once, then reuse the same object."""
    return Settings()
