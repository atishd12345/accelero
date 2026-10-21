FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && mkdir -p /data

ENV ACCELERO_HOST=0.0.0.0
ENV ACCELERO_PORT=8000
ENV ACCELERO_DB=/data/accelero.db
ENV ACCELERO_SEED=true

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["accelero"]
