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
COPY config.yaml ./

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app
USER appuser

# Expose both FastAPI and MCP ports
EXPOSE 5006
EXPOSE 8006

# Command to start the server
CMD ["/app/.venv/bin/python", "src/main.py"]