# QuickCart

[![CI](https://github.com/MohdAsif-AIML25/quickcart-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/MohdAsif-AIML25/quickcart-backend/actions/workflows/ci.yml)

An e-commerce application: a **FastAPI** backend with a **React** frontend,
PostgreSQL, Redis, and Docker. Users browse products, fill a cart, and place
orders. Admins manage the catalogue and see every order.

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL 16 · Redis 7 · JWT · React 19 · Vite · nginx · Docker Compose · GitHub Actions

## Features

- **Authentication:** registration, login, JWT access and refresh tokens, bcrypt password hashing.
- **Authorization:** role-based access control (`user`, `admin`), enforced by the API.
- **Catalogue:** pagination, category filter, search, soft delete, validated image upload (JPEG, PNG, WebP).
- **Cart and checkout:** one database transaction with row-level locks, so two buyers cannot both get the last unit.
- **Orders:** each order line stores a snapshot of the product name and price at the time of sale.
- **Caching:** product listings are cached in Redis and invalidated whenever product data changes.
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
(production) forward `/api/...` to FastAPI and remove the `/api` prefix. The
result: no CORS configuration, and in production the API, the database, and
Redis publish no port at all.

```text
app/
  api/routes/     HTTP layer: one file per resource, no business logic
  api/deps.py     shared dependencies: database session, current user, admin check
  services/       business logic: checkout, cart, cache, uploads
  models/         SQLAlchemy tables
  schemas/        Pydantic request and response models
  core/           settings, security (JWT, bcrypt), errors, rate limiting, logging
alembic/          database migrations
tests/            pytest suite (runs against real PostgreSQL and Redis)
frontend/         React app (Vite), nginx config, Dockerfile
```

## Quick start (Windows, PowerShell)

Requirements: Python 3.12, Node.js 22, Docker Desktop.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env          # then set JWT_SECRET_KEY to a long random value
docker compose up -d db redis        # PostgreSQL on port 5433, Redis on 6379
alembic upgrade head                 # create the tables
uvicorn app.main:app --reload
```

The API documentation is at <http://127.0.0.1:8000/docs>.

In a second terminal, start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Sign up, then give your account the admin role:

```powershell
python -m scripts.promote_admin you@example.com
```

Reload the page. An **Admin** link appears, where you can create products.

## Tests

```powershell
docker compose up -d db redis
python -m pytest
python -m pytest --cov --cov-report=term-missing
ruff check .
```

The suite has 79 tests and runs against a **real** PostgreSQL database
(`quickcart_test`, created automatically) and a real Redis instance (database
15). Your development data is never touched: the fixtures refuse to run
against a database whose name does not end in `_test`.

Notable tests:

- **Concurrent checkout:** eight buyers race for three units. Exactly three succeed, five get `409`, and stock ends at `0`. The test fails if the row lock is removed.
- **Rollback:** when one cart line is out of stock, nothing changes: no order, no stock change, the cart is intact.
- **Snapshot:** an order keeps the product name and price it was placed with, after the product is renamed and repriced.
- **Graceful degradation:** the catalogue and login keep working when Redis is down.

## Run the whole stack with Docker

```powershell
docker compose up -d --build         # db, redis, and the API on http://localhost:8000
```

The production stack adds nginx and the built frontend, and publishes only port 80:

```powershell
Copy-Item .env.prod.example .env.prod      # then set a password and a JWT secret
docker compose -p quickcart-prod -f docker-compose.prod.yml --env-file .env.prod up -d --build
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
| `POST /orders/checkout` | user | turn the cart into an order |
| `GET /orders/me` | user | my orders |
| `GET /admin/orders` | admin | all orders |
| `GET /health`, `GET /health/ready` | public | liveness and readiness |

Errors always have one shape: `{"error": {"code": "...", "message": "..."}}`.

## Design decisions

| Decision | Why | Trade-off |
|---|---|---|
| `SELECT ... FOR UPDATE` on the product rows during checkout, always in product-id order | Prevents overselling under concurrent checkouts; one lock order prevents deadlocks | Checkouts for the same product wait for each other |
| Name and price copied into `order_items` | An order is a historical record and must not change when the product does | The same fact is stored twice on purpose |
| Money as `Numeric` / `Decimal`, sent as strings in JSON | Floats cannot represent amounts such as 0.10 exactly | The frontend must convert strings to display them |
| Short-lived access token (15 min) plus refresh token (7 days) | A stolen access token is useful only briefly | The server checks the user's status on every request, because a JWT cannot be revoked |
| Cache invalidation by version number | One `INCR` makes every cached listing unreachable; no key scanning | Old keys stay in Redis until their TTL ends |
| Redis is optional | Cache and rate limiter fail open, so a Redis outage does not take the shop down | During an outage there is no login rate limit |
| Soft delete for products | Old orders still reference the product | Queries must filter on `is_active` |
| Tests on real PostgreSQL and Redis | Row locks, constraints, and cache behaviour do not exist in SQLite or mocks | The suite needs Docker and is slower than unit tests |
| Tokens in `localStorage` | Simple, and they survive a page reload | A script injected into the page could read them; an `httpOnly` cookie is stricter |
| Migrations run when the API container starts | One command deploys everything | With several API copies, migrations must become a separate step |

## Continuous integration

Every push and pull request runs three jobs in GitHub Actions: backend lint and
tests (with PostgreSQL and Redis service containers), frontend lint and build,
and a build of both Docker images.
