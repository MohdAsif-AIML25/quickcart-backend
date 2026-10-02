# 1. Change the router import line to:
from app.api.routes import auth, health
# 2. Add this import:
from app.core.exceptions import register_exception_handlers
from app.api.routes import admin_products, auth, health, products
# ...
    app.include_router(products.router)

from app.api.routes import admin_products, auth, cart, health, products
# ...
    app.include_router(cart.router)
# 3. Inside create_app(), right after `app = FastAPI(...)`:
    register_exception_handlers(app)

# ...and after app.include_router(health.router):
    app.include_router(auth.router)

from app.api.routes import admin_orders, admin_products, auth, cart, health, orders, products
# ...
    app.include_router(orders.router)
    app.include_router(admin_orders.router)