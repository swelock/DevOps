FROM python:3.12.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_ENGINE=sqlite \
    DATABASE_PATH=/app/instance/campus.sqlite3

WORKDIR /app
COPY requirements.txt requirements-lock.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 campus \
    && useradd --uid 10001 --gid campus --no-create-home --shell /usr/sbin/nologin campus \
    && mkdir -p /app/instance \
    && chown campus:campus /app/instance

COPY campus ./campus
COPY migrations ./migrations
COPY deploy/postgresql/schema.sql ./deploy/postgresql/schema.sql

USER 10001:10001
VOLUME ["/app/instance"]
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--access-logfile", "-", "--error-logfile", "-", "campus:create_app()"]
