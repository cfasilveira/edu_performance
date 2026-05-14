# 🚀 DEPLOY CHECKLIST — EduAnalytics MVP v0.1.0

> Execute esta checklist **antes de cada deploy** em novo ambiente.

---

## Pré-Deploy

- [ ] `.env` configurado com `POSTGRES_PASSWORD` seguro (≥ 16 chars, aleatório)
- [ ] `.env` **não** está no histórico git: `git log --all -- .env` → vazio
- [ ] `ollama list` mostra `mistral` (ou modelo configurado em `pedagogical_rules.json`)
- [ ] `contracts/pedagogical_rules.json` validado: `python3 scripts/validate_contracts.py`
- [ ] RAM disponível: `free -h` mostra ≥ 15 GB livres

## Build & Infraestrutura

- [ ] `docker compose config --quiet` → 0 warnings
- [ ] `docker compose build --no-cache` → sem erros
- [ ] `docker compose up -d`
- [ ] Aguardar ≤ 60s: `docker compose ps` mostra ambos `healthy`
- [ ] Testar app: `curl http://localhost:8501/_stcore/health` → `200 OK`
- [ ] Testar Ollama do container:
  ```bash
  docker exec edu-mvp curl -s http://host.docker.internal:11434/api/tags
  ```

## Testes

- [ ] `bash scripts/run_tests_local.sh --fast` → verde
- [ ] `python3 scripts/security_audit.py` → sem FAIL
- [ ] `docker stats edu-mvp --no-stream` → MEM ≤ 4 GB, CPU ≤ 400%

## Pós-Deploy

- [ ] Testar fluxo completo: Upload → Agrupamento → IA → Aprovação → Audit Export
- [ ] Confirmar que logs não contêm PII: `docker compose logs edu-mvp | grep -i "nome\|cpf\|email"`
- [ ] Criar backup inicial do banco: `docker exec edu-db pg_dump -U edu_user edu_mvp > backup_inicial.sql`

---

**Aprovado por:** _________________ **Data:** _________________
