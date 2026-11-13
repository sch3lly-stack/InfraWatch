# ---- frontend build ----
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- server runtime ----
FROM python:3.12-slim AS server
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN useradd --system --create-home --uid 10001 infrawatch
WORKDIR /app
COPY server/pyproject.toml ./server/pyproject.toml
COPY server/infrawatch_server ./server/infrawatch_server
RUN pip install ./server
COPY --from=web /web/dist /app/frontend/dist
ENV INFRAWATCH_FRONTEND_DIR=/app/frontend/dist
USER infrawatch
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/api/v1/health')"
CMD ["uvicorn", "--factory", "infrawatch_server.main:app_factory", "--host", "0.0.0.0", "--port", "8000"]
