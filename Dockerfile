# Production web container for AWS Elastic Beanstalk Docker on AL2023.
# SINGLE instance / SINGLE Gunicorn worker until simulation jobs are moved to a queue.
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    MIDSHIRE_WORKERS=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --system --uid 10001 --create-home midshire
USER midshire

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()" || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", \
     "--timeout", "120", "--graceful-timeout", "45", "--access-logfile", "-", \
     "--error-logfile", "-", "uec_hybrid.midshire.server:create_app()"]
