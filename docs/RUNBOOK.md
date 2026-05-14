# 📖 RUNBOOK — EduAnalytics MVP

> **Versão**: 0.1.0-mvp | **Ambiente**: Local (Ubuntu 24.04 + Docker 28.2.2)

---

## ⚡ Início Rápido (5 minutos)

```bash
# 1. Clonar e configurar
cd ~/Projetos/edu_performance
cp .env.example .env
# edite .env e defina POSTGRES_PASSWORD

# 2. Subir os serviços
docker compose up -d

# 3. Aguardar healthchecks (≤ 60s)
docker compose ps   # ambos devem mostrar "healthy"

# 4. Acessar a aplicação
xdg-open http://localhost:8501
```

---

## Pré-requisitos

| Requisito | Versão mínima | Verificar |
|-----------|--------------|-----------|
| Docker | 28.2.2 | `docker --version` |
| Docker Compose | v2+ | `docker compose version` |
| Ollama | qualquer | `ollama --version` |
| Mistral no Ollama | — | `ollama list` → deve ter `mistral` |
| RAM livre | ~15 GB | `free -h` |

---

## Verificar Ollama

```bash
# Mistral deve estar disponível
ollama list | grep mistral

# Se não estiver:
ollama pull mistral

# Testar conectividade do container ao host
docker exec edu-mvp curl -s http://host.docker.internal:11434/api/tags | python3 -m json.tool
```

---

## Comandos Úteis

```bash
# Ver logs em tempo real
docker compose logs -f edu-mvp
docker compose logs -f edu-db

# Ver uso de recursos
docker stats edu-mvp edu-db --no-stream

# Reiniciar apenas a aplicação (sem perder dados)
docker compose restart edu-mvp

# Parar tudo (preserva volumes)
docker compose down

# Parar E remover volumes (CUIDADO: apaga dados)
docker compose down -v

# Conectar ao banco diretamente
docker exec -it edu-db psql -U edu_user -d edu_mvp
```

---

## Executar Testes

```bash
# Instalar dependências de dev (apenas na primeira vez)
uv sync --all-extras

# Suite rápida (sem carga)
bash scripts/run_tests_local.sh --fast

# Suite completa
bash scripts/run_tests_local.sh

# Apenas segurança/LGPD
bash scripts/run_tests_local.sh --security-only

# Auditoria de segurança
python3 scripts/security_audit.py

# Validar contratos
python3 scripts/validate_contracts.py
```

---

## Trocar Modelo LLM

```bash
# 1. Baixar o novo modelo no Ollama
ollama pull llama3   # ou qwen2, gemma2

# 2. Atualizar o contrato (sem alterar código)
# Edite contracts/pedagogical_rules.json:
#   "models" → "default": "llama3"

# 3. Verificar que o modelo está no enum
# contracts/data_models.py → SupportedModel

# 4. Reiniciar a aplicação
docker compose restart edu-mvp
```

---

## Solução de Problemas

### App não inicia
```bash
docker compose logs edu-mvp | tail -50
# Verificar: porta 8501 livre? DB healthy?
```

### Ollama não responde do container
```bash
# Testar host-gateway
docker exec edu-mvp curl http://host.docker.internal:11434/api/tags
# Se falhar: verificar que Ollama está rodando no host
systemctl status ollama   # ou: ollama serve
```

### Banco de dados não conecta
```bash
docker compose ps edu-db   # deve ser "healthy"
docker compose logs edu-db | tail -20
# Verificar POSTGRES_PASSWORD no .env
```

### Memória insuficiente
```bash
docker stats --no-stream
# edu-mvp deve usar ≤ 4 GB
# Se Ollama + App > 24 GB: pare outros processos ou reduza cpus no compose
```

### Reiniciar do zero
```bash
docker compose down -v          # remove volumes
docker compose up -d            # recria tudo
# Banco é reinicializado via config/init.sql
```

---

## Backup dos Dados

```bash
# Dump do banco
docker exec edu-db pg_dump -U edu_user edu_mvp > backup_$(date +%Y%m%d).sql

# Restaurar
docker exec -i edu-db psql -U edu_user -d edu_mvp < backup_YYYYMMDD.sql
```

---

## Preparação para Produção (Futuro)

Itens a completar antes de produção:
- [ ] Habilitar TLS no docker-compose (nginx reverse proxy)
- [ ] Trocar `POSTGRES_PASSWORD` por secret manager
- [ ] Configurar GitHub Actions CI (já em `ci/cd-pipeline.yml`)
- [ ] Configurar retention policy nos audit_logs
- [ ] Implementar multi-tenant (adicionar tenant_id nos filtros de query)
