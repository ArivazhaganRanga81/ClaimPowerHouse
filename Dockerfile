FROM node:22-bookworm-slim AS web-build
WORKDIR /build/apps/web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CPH_ENV=production \
    CPH_DATA_ROOT=/data \
    CPH_DATABASE_URL=sqlite:////data/db/claim_powerhouse.db \
    CPH_CHROMA_PATH=/data/chroma \
    CPH_WEB_ROOT=/app/apps/web/dist \
    CPH_AUTO_SEED=true
WORKDIR /app
RUN addgroup --system cph && adduser --system --ingroup cph cph
COPY pyproject.toml README.md ./
COPY apps/api ./apps/api
COPY --from=web-build /build/apps/web/dist ./apps/web/dist
RUN python -m pip install --no-cache-dir ".[rag,mcp,llm]"
RUN mkdir -p /data && chown -R cph:cph /app /data
USER cph
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "apps/api", "--host", "0.0.0.0", "--port", "8000"]

