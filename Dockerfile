# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_NO_DEV=1

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project


FROM python:3.12-slim

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_URL=sqlite:////data/skor-risiko.db

RUN useradd --create-home --uid 10001 skor \
    && mkdir /data \
    && chown skor:skor /data

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY bot ./bot
COPY skills ./skills
COPY scripts ./scripts
COPY tests/fixtures ./tests/fixtures

RUN chown -R skor:skor /app/bot/data

USER skor
VOLUME ["/data"]
CMD ["python", "-m", "bot"]
