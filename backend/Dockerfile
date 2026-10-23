FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy
WORKDIR /srv
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir -e . 2>/dev/null || pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic requests pyyaml jinja2 "psycopg[binary]" playwright pywebpush
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY config /config
ENV VVT_CONFIG=/config VVT_RULES=/config/rules.yaml VVT_REPORT_DIR=/data/reports
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
