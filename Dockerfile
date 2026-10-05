# syntax=docker/dockerfile:1

# ---- Stage 1: build the virtual environment --------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Copy ONLY requirements first: Docker caches this layer, so the slow
# "pip install" re-runs only when requirements.txt changes, not on every code edit.
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install -r requirements.txt


# ---- Stage 2: the small image that actually runs ---------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Never run a web server as root: if the app is compromised, the attacker
# gets an unprivileged user, not the whole container.
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

RUN mkdir -p /app/uploads && chown -R app:app /app/uploads

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" || exit 1

# 1. Apply database migrations.  2. Start the API.
# "exec" replaces the shell with uvicorn, so Docker's stop signal reaches it
# directly and the server shuts down gracefully.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
