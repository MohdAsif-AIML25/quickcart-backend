# QuickCart - Production E-Commerce Backend API

FastAPI | PostgreSQL | SQLAlchemy 2.0 | Alembic | Redis | JWT | Docker

> Work in progress: built as a 7-day, 10-task portfolio project.

## Quick start (Windows)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
docker compose up -d          # PostgreSQL (5433) + Redis (6379)
alembic upgrade head          # create the tables
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs

## Run the tests

```powershell
pytest
```
