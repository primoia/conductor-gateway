# 1. Build stage
FROM python:3.11-slim AS builder
WORKDIR /app
RUN pip install poetry
COPY pyproject.toml poetry.lock ./
# Install dependencies only
RUN poetry config virtualenvs.in-project true && \
    poetry install --only=main --no-root

# 2. Final stage
FROM python:3.11-slim
WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy virtual environment and code
COPY --from=builder /app/.venv ./.venv
COPY src/ ./src/

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

# Command to start the server - use uvicorn with factory function
# timeout-keep-alive controls how long to wait for clients (30 minutes = 1800s)
CMD ["/app/.venv/bin/uvicorn", "src.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--timeout-keep-alive", "1800"]