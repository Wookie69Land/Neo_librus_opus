# Multi-stage Dockerfile optimized for UV-managed virtualenvs.
#
# Builder stage uses `uv` to create a frozen virtual environment. Runner
# stage reuses the environment without installing `uv` again to keep the
# final image minimal.
FROM python:3.12-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install build dependencies and `uv` tool used to build reproducible venvs
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc build-essential git \
    && python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir uv

# Copy lock / project metadata. If you use pyproject.toml + uv.lock, uv
# will create the venv exactly as declared. We include requirements.txt
# as a fallback for developer setups.
COPY app/pyproject.toml app/uv.lock app/README.md app/requirements.txt* /app/

# Build the virtualenv using uv. This build requires `pyproject.toml`
# and `uv.lock` from the `app/` directory to create a reproducible environment.
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir uv \
    && uv sync --frozen

FROM python:3.12-slim AS runner

ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# Copy the frozen virtualenv from the builder image
COPY --from=builder /app/.venv /app/.venv

# Copy project source
COPY . /app

EXPOSE 8000

# Default command for local testing; production compose overrides this.
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "app.core.asgi:application", "-b", "0.0.0.0:8000"]
