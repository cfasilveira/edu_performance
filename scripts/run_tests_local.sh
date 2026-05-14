#!/usr/bin/env bash
# =============================================================================
# scripts/run_tests_local.sh
# CI Local para o EduAnalytics MVP — substitui GitHub Actions no ambiente dev.
# Uso: bash scripts/run_tests_local.sh [--fast] [--security-only]
#
# Flags:
#   --fast          Pula testes de carga (mais rápido para dev cotidiano)
#   --security-only Roda apenas suite de segurança e LGPD
# =============================================================================

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

FAST=false
SECURITY_ONLY=false

for arg in "$@"; do
  case $arg in
    --fast) FAST=true ;;
    --security-only) SECURITY_ONLY=true ;;
  esac
done

echo ""
echo "════════════════════════════════════════════════════════════"
echo "🛡️  EduAnalytics MVP — CI Local"
echo "════════════════════════════════════════════════════════════"

# ─── 1. Lint & Type Check ────────────────────────────────────────────────────
echo ""
echo "▶ [1/4] Lint & Type Check"
uv run ruff check src/ tests/
uv run mypy --strict src/

# ─── 2. Validação de Contratos ───────────────────────────────────────────────
echo ""
echo "▶ [2/4] Validação de Contratos & Segurança Estática"
python3 scripts/validate_contracts.py

# ─── 3. Testes ───────────────────────────────────────────────────────────────
echo ""
echo "▶ [3/4] Testes"

if [ "$SECURITY_ONLY" = true ]; then
  echo "  → Modo: security-only"
  uv run pytest tests/security/ tests/static/ \
    -v --tb=short \
    --cov=src --cov-report=term-missing
elif [ "$FAST" = true ]; then
  echo "  → Modo: fast (sem testes de carga)"
  uv run pytest tests/ \
    --ignore=tests/load/ \
    -n auto \
    -v --tb=short \
    --cov=src --cov-report=term-missing \
    --cov-fail-under=85
else
  echo "  → Modo: completo"
  uv run pytest tests/ \
    -n auto \
    -v --tb=short \
    --cov=src \
    --cov-report=term-missing \
    --cov-report=html:reports/coverage_html \
    --junitxml=reports/junit.xml \
    --cov-fail-under=85
fi

# ─── 4. Docker Compose Validate ──────────────────────────────────────────────
echo ""
echo "▶ [4/4] Docker Compose Validate"

if [ -f "docker-compose.yml" ]; then
  docker compose config --quiet && echo "  ✅ docker-compose.yml válido"
else
  echo "  ⚠️  docker-compose.yml não encontrado — Agente 1 ainda não entregou"
fi

# Verificar que .env não está commitado
if git log --all --name-only --format="" 2>/dev/null | grep -q "^\.env$"; then
  echo "  ❌ CRÍTICO: .env foi commitado! Remova do histórico antes de prosseguir."
  exit 1
else
  echo "  ✅ .env não está no histórico git"
fi

# ─── Resultado ───────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════"
echo "✅ CI Local concluído com sucesso!"
echo "   Relatórios em: reports/"
echo "════════════════════════════════════════════════════════════"
