# SMN — GCP Marketplace Container Packaging

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

LABEL app.kubernetes.io/name="smn"
LABEL app.kubernetes.io/version="0.1.0"
LABEL vendor="SMN"
LABEL description="Secure Multi-agent Network — Deploy, govern, and scale AI agents safely."

ENV SMN_HOST=0.0.0.0
ENV SMN_PORT=8000

CMD ["smn", "serve", "--host", "0.0.0.0", "--port", "8000"]
