FROM mcr.microsoft.com/playwright/python:v1.49.1-noble
WORKDIR /srv
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/tests ./tests
COPY backend/migrations ./migrations
COPY config /config
ENV VVT_CONFIG=/config VVT_RULES=/config/rules.yaml VVT_REPORT_DIR=/data/reports VVT_DATA_DIR=/data PYTHONUNBUFFERED=1
RUN mkdir -p /data/reports
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
# API_WORKERS comes from .env (install.sh: 1 on 1–2 GB machines, 2 otherwise)
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS:-2}"]
