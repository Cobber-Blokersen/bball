FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.14-slim

RUN groupadd -r bball && useradd -r -g bball -d /app -s /sbin/nologin bball

COPY --from=builder /app/.venv /app/.venv
COPY src/ /app/src/

RUN mkdir -p /app/data && chown -R bball:bball /app/data

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8002

VOLUME ["/app/data"]

USER bball
WORKDIR /app

# CMD ["sh", "-c", "exec uvicorn bball.web.app:app --host 0.0.0.0 --port \"${PORT:-8080}\" --workers 4"]

CMD ["gunicorn", "bball.web.app:app", \
     "-w", "4", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-b", "0.0.0.0:8002", \
     "--no-control-socket", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
