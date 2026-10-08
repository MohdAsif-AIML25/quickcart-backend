# QuickCart

[![CI](https://github.com/MohdAsif-AIML25/quickcart-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/MohdAsif-AIML25/quickcart-backend/actions/workflows/ci.yml)

An e-commerce application: a **FastAPI** backend with a **React** frontend,
PostgreSQL, Redis, and Docker. Users browse products, fill a cart, and place
orders with a delivery address. Admins manage the catalogue and every order:
status, delivery date, cancellation, and deletion.

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL 16 · Redis 7 · JWT · React 19 · Vite · nginx · Docker Compose · GitHub Actions

> **Payment gateway integration is not implemented.** The only payment method
> is Cash on Delivery. The application never collects card or UPI details,
> never contacts a payment provider, and never marks an order as paid. UPI and
> card appear on the checkout page as *unavailable*.

## Features

- **Authentication:** registration, login, JWT access and refresh tokens, bcrypt password hashing.
- **Authorization:** role-based access control (`user`, `admin`), enforced by the API.
- **Catalogue:** pagination, category filter, search, soft delete, validated image upload (JPEG, PNG, WebP).
- **Cart and checkout:** one database transaction with row-level locks, so two buyers cannot both get the last unit and a double-clicked checkout creates one order.
- **Delivery address:** checkout requires a recipient name, phone number, address lines, city, state, postal code and country. The API validates every field and the order keeps its own copy (a snapshot).
- **Payment mode:** Cash on Delivery. `payment_method` and `payment_status` are stored separately from the order status; a new order is `pending`, not `paid`.
- **Order life cycle:** `confirmed` → `processing` → `shipped` → `delivered`, or `cancelled` before shipping. Only admins change the status and the estimated delivery date; the API rejects every other transition.
- **Order deletion:** an admin can soft-delete a confirmed order. It disappears from all listings, its database row stays, and its stock is returned exactly once, also under repeated or concurrent requests.
- **Orders:** each order line stores a snapshot of the product name and price at the time of sale. Customers see only their own orders.
- **Caching:** product listings are cached in Redis and invalidated whenever product data or stock changes.
- **Rate limiting:** login attempts are limited per IP address with Redis.
- **Frontend:** a single-page React app with automatic token refresh.

## Architecture

```text
DEVELOPMENT                                   PRODUCTION (docker-compose.prod.yml)

Browser ── http://localhost:5173              Browser ── http://SERVER/
   │                                             │
   ▼                                             ▼
Vite dev server ──/api/...──▶ FastAPI :8000   nginx ──/api/...──▶ FastAPI ──▶ PostgreSQL
(React, hot reload)              │            (serves the built      │
                                 ▼             React files)          └──────▶ Redis
                        PostgreSQL · Redis
```

The browser always talks to **one origin**. Vite (development) and nginx
(Docker) forward `/api/...` to FastAPI and remove the `/api` prefix. The
result: no CORS configuration, and in production the API, the database, and
Redis publish no port at all.

```text
app/
  api/routes/     HTTP layer: one file per resource, no business logic
  api/deps.py     shared dependencies: database session, current user, admin check
  services/       business logic: checkout, orders, cart, cache, uploads
  models/         SQLAlchemy tables, order statuses and their allowed transitions
  schemas/        Pydantic request and response models
  core/           settings, security (JWT, bcrypt), errors, rate limiting, logging
alembic/          database migrations
tests/            pytest suite (runs against real PostgreSQL and Redis)
frontend/         React app (Vite), nginx config, Dockerfile
```

## Quick start (Windows, PowerShell)

Requirements: Python 3.12, Node.js 22, Docker Desktop.

Run these commands in the `quickcart-backend` folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env          # then set JWT_SECRET_KEY to a long random value
docker compose up -d db redis        # PostgreSQL on port 5433, Redis on 6379
alembic upgrade head                 # create or update the tables
uvicorn app.main:app --reload
```

The API documentation is at <http://127.0.0.1:8000/docs>.

In a second terminal, start the frontend from the `quickcart-backend\frontend` folder:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Sign up, then give your account the admin role
(run this in the `quickcart-backend` folder):

```powershell
python -m scripts.promote_admin you@example.com
```

Reload the page. An **Admin** link appears, where you can create products and manage orders.

## Demo walkthrough

1. **Admin:** open **Admin → Products**, create a product with stock `10`, and upload an image.
2. **Customer:** sign up with a second account, add the product to the cart, and open **Cart**. *Remove* still works here: a customer can change the cart freely before checkout.
3. Click **Proceed to checkout**. Submit the empty form: every invalid field shows its own message. UPI and card are visible but disabled.
4. Fill in the address, keep **Cash on Delivery**, and click **Place order**. The order appears under **Orders** with status *Confirmed*, payment *Cash on Delivery · Payment pending*, and estimated delivery *Not scheduled*. The product stock is now `9`.
5. **Admin:** open **Admin → Orders → Manage**. Change the status to *Processing* and set an estimated delivery date. The customer sees both after a reload.
6. Place a second order as the customer. As admin, click **Delete order** and confirm. The order disappears from both order lists and the stock returns to `9`. The row is still in the database:

   ```powershell
   docker compose exec db psql -U quickcart -d quickcart -c "SELECT id, status, deleted_at, stock_restored_at FROM orders ORDER BY id;"
   ```

7. Move the first order to *Shipped*, then *Delivered*. The delivery time is recorded, the payment status is still *pending* (nothing in this application confirms a payment), and **Delete order** is disabled.

## Order rules

| Current status | Admin may change it to | Delete allowed |
|---|---|---|
| `confirmed` | `processing`, `cancelled` | yes |
| `processing` | `shipped`, `cancelled` | no |
| `shipped` | `delivered` | no |
| `delivered` | nothing (final) | no |
| `cancelled` | nothing (final) | no |

- Any other change returns `409` with the message `Cannot change order status from 'x' to 'y'`.
- **Cancelling** and **deleting** both return the order's units to stock. They call one shared function that locks the order row and sets `stock_restored_at`, so the stock cannot be returned twice.
- Becoming `delivered` sets `delivered_at`. Cancelling clears the estimated delivery date.
- The estimated delivery date cannot be earlier than the order date and cannot be changed on a delivered or cancelled order.
- `payment_status` never changes when the order status changes.
- Customers have no endpoint to delete an order or change its status. The admin endpoints return `403` for them.

**Orders placed before this version** have no address and no payment
information. The migration adds the new columns as `NULL` and changes no
existing row; the API returns `null` and the pages show *Not recorded*. No
historical value is invented.

## Tests

Run these commands in the `quickcart-backend` folder:

```powershell
docker compose up -d db redis
python -m pytest
python -m pytest --cov --cov-report=term-missing
ruff check .
```

Frontend checks, in the `quickcart-backend\frontend` folder:

```powershell
npm run lint
npm run build
```

The suite has 170 tests and runs against a **real** PostgreSQL database
(`quickcart_test`, created automatically) and a real Redis instance (database
15). Your development data is never touched: the fixtures refuse to run
against a database whose name does not end in `_test`.

Notable tests:

- **Concurrent checkout:** eight buyers race for three units. Exactly three succeed, five get `409`, and stock ends at `0`. The test fails if the row lock is removed.
- **Exactly-once stock restoration:** six delete requests (and a mix of delete and cancel requests) hit one order at the same moment. One succeeds and the stock is returned once. The tests fail if the order row lock is removed.
- **Double-submitted checkout:** the same user sends checkout twice at once. One order is created.
- **Rollback:** when one cart line is out of stock, nothing changes: no order, no stock change, the cart is intact.
- **Ownership and roles:** a customer gets `404` for another user's order and `403` for every admin order operation.
- **Status transitions:** every transition that is not in the table above is rejected and leaves the order unchanged.
- **Migration:** rows written with the previous schema survive the upgrade unchanged, with `NULL` in every new column.
- **Snapshot:** an order keeps the product name and price it was placed with, after the product is renamed and repriced.
- **Graceful degradation:** the catalogue and login keep working when Redis is down.

## Run the whole stack with Docker

Run every command in the `quickcart-backend` folder (the one that contains
`docker-compose.yml`). A `.env` file must exist there (see Quick start).

```powershell
docker compose up -d --build      # build and start: db, redis, api, web
docker compose ps                 # all four services should be "healthy"
```

| Address | What it serves |
|---|---|
| <http://localhost:8080> | the shop (nginx with the built React app) |
| <http://localhost:8080/api/health> | the API through nginx, as the browser reaches it |
| <http://localhost:8000/docs> | the API documentation (Swagger), directly from the API container |

**Migrations** run automatically each time the `api` container starts
(`alembic upgrade head`). To run or inspect them yourself:

```powershell
docker compose exec api alembic upgrade head
docker compose exec api alembic current
```

**Logs:**

```powershell
docker compose logs -f api        # the API (Ctrl+C stops following, not the container)
docker compose logs -f web        # nginx
docker compose logs --tail 100    # the last 100 lines of every service
```

**First admin in the Docker stack:** sign up at <http://localhost:8080>, then:

```powershell
docker compose exec db psql -U quickcart -d quickcart -c "UPDATE users SET role = 'admin' WHERE email = 'you@example.com';"
```

**Shutdown:**

```powershell
docker compose down               # stop and remove the containers; ALL DATA IS KEPT
```

The database and the uploaded product images live in two named volumes,
`postgres_data` and `uploads_data`. They survive `docker compose down` and
`docker compose up -d --build`. Only `docker compose down -v` deletes them, so
do not add `-v` unless you want to lose every user, product, order and image.

Uploaded images are stored by the API in `uploads_data` and reach the browser
as `/api/uploads/products/<file>`: nginx forwards the request to the API,
which serves the file.

### Production stack

The production stack publishes only port 80 and does not expose the API,
PostgreSQL or Redis. Run it in the `quickcart-backend` folder:

```powershell
Copy-Item .env.prod.example .env.prod      # then set a password and a JWT secret
docker compose -p quickcart-prod -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -p quickcart-prod -f docker-compose.prod.yml --env-file .env.prod logs -f api
docker compose -p quickcart-prod -f docker-compose.prod.yml --env-file .env.prod down
```

| Address | What it serves |
|---|---|
| <http://localhost/> | the shop |
| <http://localhost/api/docs> | the API documentation |

Deployment to a single AWS EC2 instance is described in [docs/aws-deployment.md](docs/aws-deployment.md).

## API overview

| Method and path | Access | Purpose |
|---|---|---|
| `POST /auth/register` | public | create an account |
| `POST /auth/login` | public, rate limited | get an access and a refresh token |
| `POST /auth/refresh` | refresh token | get new tokens |
| `GET /auth/me` | user | the current user |
| `GET /products`, `GET /products/{id}` | public | catalogue with `page`, `limit`, `category`, `search` |
| `POST /admin/products`, `PATCH`, `DELETE /admin/products/{id}` | admin | manage products |
| `POST /admin/products/{id}/image` | admin | upload a product image |
| `GET /cart`, `POST /cart/items`, `DELETE /cart/items/{id}` | user | the cart |
| `POST /orders/checkout` | user | turn the cart into an order; body: `shipping_address`, `payment_method` |
| `GET /orders/me` | user | my orders |
| `GET /orders/{id}` | user | one of my orders (`404` for another user's order) |
| `GET /admin/orders` | admin | all orders that are not deleted |
| `PATCH /admin/orders/{id}` | admin | change `status` and/or `estimated_delivery_date` |
| `DELETE /admin/orders/{id}` | admin | soft-delete a confirmed order and return its stock |
| `GET /health`, `GET /health/ready` | public | liveness and readiness |

A checkout request:

```json
{
  "shipping_address": {
    "recipient_name": "Asha Verma",
    "phone": "+91 98765 43210",
    "address_line1": "221B MG Road",
    "address_line2": "Near City Mall",
    "city": "Bengaluru",
    "state": "Karnataka",
    "postal_code": "560001",
    "country": "India"
  },
  "payment_method": "cod"
}
```

Errors raised by the application always have one shape:
`{"error": {"code": "...", "message": "..."}}`. Request validation errors
(`422`) use FastAPI's standard shape, `{"detail": [{"loc": [...], "msg": "..."}]}`,
which names every invalid field.

## Design decisions

| Decision | Why | Trade-off |
|---|---|---|
| `SELECT ... FOR UPDATE` on the product rows during checkout, always in product-id order | Prevents overselling under concurrent checkouts; one lock order prevents deadlocks | Checkouts for the same product wait for each other |
| Row lock on the order plus a `stock_restored_at` marker for cancel and delete | Two requests for the same order run one after the other, and the second sees the marker, so stock is returned once | Admin actions on one order wait for each other |
| Soft delete for orders (`deleted_at`) | The record stays available for audits and accounting | Every order query must filter on `deleted_at` |
| Allowed status transitions in one table, sent to the frontend as `allowed_next_statuses` | The rule exists once; the admin page cannot offer a change the API would refuse | The response is slightly larger |
| Address copied onto the order as separate columns | An order must show where it was sent, whatever the customer does later; columns can be validated and queried | The order table is wider |
| New order columns are `NULL` for old orders | Unknown stays unknown; no invented history | The frontend must handle "not recorded" |
| Name and price copied into `order_items` | An order is a historical record and must not change when the product does | The same fact is stored twice on purpose |
| Money as `Numeric` / `Decimal`, sent as strings in JSON | Floats cannot represent amounts such as 0.10 exactly | The frontend must convert strings to display them |
| Short-lived access token (15 min) plus refresh token (7 days) | A stolen access token is useful only briefly | The server checks the user's status on every request, because a JWT cannot be revoked |
| Cache invalidation by version number | One `INCR` makes every cached listing unreachable; no key scanning | Old keys stay in Redis until their TTL ends |
| Redis is optional | Cache and rate limiter fail open, so a Redis outage does not take the shop down | During an outage there is no login rate limit |
| Soft delete for products | Old orders still reference the product | Queries must filter on `is_active` |
| Tests on real PostgreSQL and Redis | Row locks, constraints, and cache behaviour do not exist in SQLite or mocks | The suite needs Docker and is slower than unit tests |
| Tokens in `localStorage` | Simple, and they survive a page reload | A script injected into the page could read them; an `httpOnly` cookie is stricter |
| Migrations run when the API container starts | One command deploys everything | With several API copies, migrations must become a separate step |

## Known limitations

- **No payment gateway.** Cash on Delivery only. `payment_status` stays `pending`: there is no endpoint yet to record that cash was collected, and no refund flow.
- Customers cannot cancel their own orders; only an admin can.
- An order can be cancelled only before it ships. Returns after delivery are not modelled.
- The postal code is checked strictly for India (6-digit PIN code) and only loosely for other countries. The country is free text, not a fixed list.
- A deleted order cannot be restored through the API.
- The admin order list shows the customer's user id, not their name or email.

## Continuous integration

Every push to `main` and every pull request runs three jobs in GitHub Actions:
backend lint and tests (with PostgreSQL and Redis service containers), frontend
lint and build, and a build of both Docker images.
