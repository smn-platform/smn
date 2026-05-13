# SMN — AWS Marketplace Container Packaging
#
# This Dockerfile extends the base image for AWS Marketplace distribution.
# Includes marketplace-specific metering and entitlement checks.

FROM python:3.12-slim AS base

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir ".[production]"

COPY src/ src/
COPY policies/ policies/
COPY alembic/ alembic/
COPY alembic.ini .

RUN useradd --create-home smn
USER smn

EXPOSE 8000

# AWS Marketplace metadata
LABEL com.amazonaws.marketplace.manifestversion="1.0"
LABEL com.amazonaws.marketplace.product-id="smn-secure-multi-agent-network"
LABEL vendor="SMN"
LABEL description="Secure Multi-agent Network — Deploy, govern, and scale AI agents safely."

ENV SMN_HOST=0.0.0.0
ENV SMN_PORT=8000

CMD ["smn", "serve", "--host", "0.0.0.0", "--port", "8000"]
