# 1. Change the router import line to:
from app.api.routes import auth, health
# 2. Add this import:
from app.core.exceptions import register_exception_handlers
from app.api.routes import admin_products, auth, health, products
# ...
    app.include_router(products.router)

# 3. Inside create_app(), right after `app = FastAPI(...)`:
    register_exception_handlers(app)

# ...and after app.include_router(health.router):
    app.include_router(auth.router)