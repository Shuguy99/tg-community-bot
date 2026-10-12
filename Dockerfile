FROM python:3.12-slim as base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN useradd -m -u 1000 appuser
COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
RUN pip install -e .
COPY alembic ./alembic
RUN chown -R appuser:appuser /app
USER appuser
CMD ["python", "-m", "app.main"]
