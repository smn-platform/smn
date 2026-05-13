FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

COPY policies/ policies/

# Create non-root user with writable data directory
RUN useradd --create-home smn && mkdir -p /app/data && chown smn:smn /app/data
USER smn

ENV SMN_DATABASE_URL="sqlite+aiosqlite:///./data/smn.db"

EXPOSE 8000

CMD ["smn", "serve", "--host", "0.0.0.0", "--port", "8000"]
