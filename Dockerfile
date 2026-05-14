# syntax=docker/dockerfile:1.6
FROM python:3.12-slim AS base

# ── Metadados ──────────────────────────────────────────────────────────────
LABEL maintainer="EduAnalytics MVP" \
      version="0.1.0" \
      description="Sistema de análise de desempenho escolar com IA local"

# ── Variáveis de build ─────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_VERSION=0.4.0 \
    APP_DIR=/app

WORKDIR ${APP_DIR}

# ── Dependências de sistema (mínimas para segurança) ──────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Instalar uv ───────────────────────────────────────────────────────────
RUN pip install --no-cache-dir uv==${UV_VERSION}

# ── Copiar manifesto de dependências primeiro (cache de layer) ─────────────
COPY pyproject.toml ./
COPY uv.lock* ./

# ── Instalar dependências de runtime (sem dev tools) ──────────────────────
RUN uv sync --no-dev --frozen

# ── Copiar código-fonte ────────────────────────────────────────────────────
COPY src/ ./src/
COPY contracts/ ./contracts/


# ── Criar usuário não-root (segurança) ────────────────────────────────────
RUN useradd -m --shell /bin/false appuser \
    && mkdir -p /app/logs /app/data \
    && chown -R appuser:appuser /app

USER appuser

# ── Healthcheck ───────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

EXPOSE 8501

# ── Ponto de entrada ──────────────────────────────────────────────────────
CMD ["uv", "run", "streamlit", "run", "src/ui/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.fileWatcherType=none"]
