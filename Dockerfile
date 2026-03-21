# ==========================================
# Stage 1: Builder
# ==========================================
FROM python:3.12-slim AS builder

# Install uv directly from official image (no curl, no PATH games)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Optional: pin version for reproducibility (check latest at ghcr.io)
# COPY --from=ghcr.io/astral-sh/uv:0.6.0 /uv /uvx /bin/

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    build-essential \
    pkgconf \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock* ./

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-editable

# ==========================================
# Stage 2: Runner (your original runner stage)
# ==========================================
FROM python:3.12-slim AS runner
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    default-mysql-client \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]