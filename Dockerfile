# Multi-stage Dockerfile optimized for UV-managed virtualenvs.
#
# Builder stage uses `uv` to create a frozen virtual environment. Runner
# stage reuses the environment without installing `uv` again to keep the
# final image minimal.
# Stage 1: Builder
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /build

# 1. Define the "Safe Zone" for the virtual environment
ENV UV_PROJECT_ENVIRONMENT="/opt/venv"
ENV UV_COMPILE_BYTECODE=1

# 2. Install dependencies
# Copy config files from ROOT
COPY pyproject.toml uv.lock ./

# 3. Create the environment
RUN uv sync --frozen --no-install-project

# Stage 2: Runner
FROM python:3.12-slim AS runner
WORKDIR /app

# 4. Copy the virtual environment from the Safe Zone
COPY --from=builder /opt/venv /opt/venv

# 5. Activate the environment globally
ENV PATH="/opt/venv/bin:$PATH"

# 6. Copy the project code
COPY . .

EXPOSE 8000

# 7. Start the server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]