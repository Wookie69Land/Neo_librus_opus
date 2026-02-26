# ==========================================
# Stage 1: Builder
# ==========================================
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /build

# 1. Define the "Safe Zone" for the virtual environment
ENV UV_PROJECT_ENVIRONMENT="/opt/venv"
ENV UV_COMPILE_BYTECODE=1

# 2. Install MySQL system dependencies FIRST
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    build-essential \
    pkgconf \
    && rm -rf /var/lib/apt/lists/*

# 3. Copy config files from ROOT
COPY pyproject.toml uv.lock ./

# 4. Create the environment
RUN uv sync --frozen --no-install-project


# ==========================================
# Stage 2: Runner
# ==========================================
FROM python:3.12-slim AS runner
WORKDIR /app

# 5. Install runtime MySQL dependencies 
# (Needed so Python can talk to MySQL when the app is actually running)
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# 6. Copy the virtual environment from the Safe Zone
COPY --from=builder /opt/venv /opt/venv

# 7. Activate the environment globally
ENV PATH="/opt/venv/bin:$PATH"

# 8. Copy the project code
COPY . .

EXPOSE 8000

# 9. Start the server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]