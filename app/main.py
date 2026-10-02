from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import admin_orders, admin_products, auth, cart, health, orders, products
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    """Application factory: build and wire the app in one place (easy to test)."""
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.log_json)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="E-commerce backend: auth, product catalogue, cart, checkout and orders.",
    )
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(products.router)
    app.include_router(admin_products.router)
    app.include_router(cart.router)
    app.include_router(orders.router)
    app.include_router(admin_orders.router)

    # Serve uploaded product images at /uploads/...
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

    return app


app = create_app()
