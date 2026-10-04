# RESOLVE API image (PLAN §16.2). Multi-stage: build a venv with uv, then a slim runtime.
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
# Install dependencies first (cached unless the lockfile changes).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Install the project itself.
COPY src ./src
RUN uv sync --frozen --no-dev


FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Run as a non-root user.
RUN useradd --create-home --uid 10001 resolve
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY src ./src
COPY data/taxonomy_map.yaml ./data/taxonomy_map.yaml

USER resolve
EXPOSE 8000

# Liveness is cheap; readiness (/ready) checks Qdrant.
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "resolve.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
