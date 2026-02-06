# Meridian Commerce Platform - Production Dockerfile
# Multi-stage build for optimized image size

# =============================================================================
# Stage 1: Builder
# =============================================================================
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt

# =============================================================================
# Stage 2: Production Image
# =============================================================================
FROM python:3.11-slim as production

# Labels
LABEL maintainer="Platform Team <platform@meridian-commerce.com>"
LABEL org.opencontainers.image.title="Meridian Commerce Platform"
LABEL org.opencontainers.image.version="2.14.0"

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    # Meridian-specific
    MERIDIAN_ENV=production \
    MERIDIAN_API_HOST=0.0.0.0 \
    MERIDIAN_API_PORT=8000

# Create non-root user for security
# Note: Using UID 1000 for compatibility with most container orchestrators
RUN groupadd --gid 1000 meridian && \
    useradd --uid 1000 --gid meridian --shell /bin/bash --create-home meridian

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels and install
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache /wheels/*

# Copy application code
COPY --chown=meridian:meridian src/ /app/src/
COPY --chown=meridian:meridian config/ /app/config/
COPY --chown=meridian:meridian scripts/ /app/scripts/

# Create necessary directories
RUN mkdir -p /app/logs /app/data /app/tmp && \
    chown -R meridian:meridian /app

# Switch to non-root user
USER meridian

# Health check
# Endpoint returns 200 when app is ready to accept traffic
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Default command - use gunicorn in production for better process management
# Workers calculated as (2 * CPU cores) + 1, configured via env var
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# =============================================================================
# Stage 3: Development Image (optional, for local dev)
# =============================================================================
FROM production as development

USER root

# Install dev dependencies
COPY requirements-dev.txt .
RUN pip install --no-cache -r requirements-dev.txt

# Install additional dev tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    vim \
    less \
    postgresql-client \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

USER meridian

# Override command for development
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
