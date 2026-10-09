# One image, two roles: `web` (uvicorn) and `worker` (python -m worker). Runtime secrets come from
# the VPS .env via compose; the image contains none.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY analyzer ./analyzer
COPY web ./web
COPY worker ./worker
COPY migrations ./migrations
COPY schema ./schema
COPY corpus/seed ./corpus/seed
RUN pip install -e ".[web]"

USER app
EXPOSE 8000
CMD ["uvicorn", "web.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
