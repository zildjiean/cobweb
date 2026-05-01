FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*
COPY apps/api/pyproject.toml /app/
RUN pip install --upgrade pip && pip install --prefix=/install -e ".[]" --no-deps \
    && pip install --prefix=/install fastapi 'uvicorn[standard]' 'pydantic>=2.9' 'pydantic-settings' \
       'sqlalchemy[asyncio]' asyncpg alembic argon2-cffi 'python-jose[cryptography]' pyotp \
       'qrcode[pil]' casbin redis aio-pika boto3 loguru httpx python-multipart email-validator slowapi authlib

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PATH=/install/bin:$PATH PYTHONPATH=/install/lib/python3.12/site-packages
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -r -u 1001 -m cobweb
COPY --from=builder /install /install
WORKDIR /app
COPY apps/api /app
USER 1001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["uvicorn", "cobweb.main:app", "--host", "0.0.0.0", "--port", "8000"]
