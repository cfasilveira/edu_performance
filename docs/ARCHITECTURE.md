# 🏗️ ARCHITECTURE.md — EduAnalytics MVP

> **Versão**: 0.1.0-mvp | **Atualizado**: 2026-05-13 | **Owner**: Agente 6

---

## Visão Geral

Sistema de análise de desempenho escolar com IA local que:
1. Ingere boletins escolares (CSV/Excel) de forma segura e pseudonimizada
2. Agrupa alunos por dificuldades compartilhadas ignorando barreiras de turma
3. Gera recomendações pedagógicas via LLM local (Ollama/Mistral)
4. Exige aprovação humana antes de qualquer ação
5. Registra tudo em audit trail imutável para conformidade LGPD

---

## Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────┐
│                  Host (Ubuntu 24.04)                     │
│                                                          │
│  ┌──────────────────┐    ┌───────────────────────────┐  │
│  │  Ollama + Mistral │    │   Docker Network: edu-net │  │
│  │  :11434 (host)   │    │                           │  │
│  └────────┬─────────┘    │  ┌─────────────────────┐  │  │
│           │ host-gateway  │  │    edu-mvp          │  │  │
│           └──────────────►│  │  Streamlit :8501    │  │  │
│                           │  │  4 CPU / 4 GB RAM   │  │  │
│                           │  │                     │  │  │
│                           │  │  src/ui/   (Agent4) │  │  │
│                           │  │  src/llm/  (Agent3) │  │  │
│                           │  │  src/io/   (Agent2) │  │  │
│                           │  │  src/analytics/     │  │  │
│                           │  └──────────┬──────────┘  │  │
│                           │             │ psycopg2     │  │
│                           │  ┌──────────▼──────────┐  │  │
│                           │  │    edu-db           │  │  │
│                           │  │  PostgreSQL :5433   │  │  │
│                           │  │  2 CPU / 1 GB RAM   │  │  │
│                           │  └─────────────────────┘  │  │
│                           └───────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Camadas da Aplicação

### 1. Contratos (`/contracts/`)
Fonte única de verdade — **nunca importe schemas de outros módulos**.

| Arquivo | Conteúdo |
|---------|---------|
| `data_models.py` | Pydantic schemas: `GradeRecord`, `StudentProfile`, `GroupingResult`, `AIRecommendation`, `AuditLogEntry`, `SupportedModel` |
| `pedagogical_rules.json` | Thresholds de nota, configuração de modelos LLM, regras LGPD, limites de performance |

### 2. Backend (`src/io/`, `src/models/`, `src/analytics/`)
- **`src/io/gradebook_parser.py`**: Parsing seguro de CSV/Excel com validação em camadas
- **`src/models/grade.py`**: Helpers de hashing, sanitização e estatísticas
- **`src/analytics/grouping.py`**: Algoritmo coseno de agrupamento cross-turma

### 3. IA (`src/llm/`)
- **`client.py`**: Comunicação com Ollama via litellm — rate limit, cache, retry
- **`advisor.py`**: Lógica pedagógica — system prompt imutável, validação Pydantic, fallback

### 4. UI (`src/ui/`)
- **`app.py`**: Orquestração Streamlit — 4 tabs, estado centralizado em `session_state`
- **`components/`**: Uploader, grade table, group view, AI panel (com aprovação), audit view

---

## Fluxo de Dados

```
CSV/XLSX upload
    │
    ▼
[uploader.py] — valida extensão, tamanho, CSV injection
    │
    ▼
[gradebook_parser.py] — normaliza, pseudonimiza (SHA-256[:12]), valida Pydantic
    │
    ▼
[grouping.py] — similaridade coseno, grupos 3-15 alunos, cross-turma
    │
    ▼
[advisor.py] — system prompt constante + user msg sanitizada → Ollama
    │
    ▼
[ai_panel.py] — professor revisa + aprova + assina
    │
    ▼
[AuditLogEntry] — registro imutável (frozen=True) → export JSON
```

---

## Decisões de Arquitetura

| Decisão | Escolha | Justificativa |
|---------|---------|---------------|
| LLM | Ollama local (Mistral 7B) | LGPD: dados nunca saem do ambiente local |
| UI | Streamlit | Prototipagem rápida, sem JS custom necessário no MVP |
| DB | PostgreSQL 16 | ACID, extensível para multi-escola futuro |
| Schemas | Pydantic v2 strict | Validação em runtime, type safety |
| Abstração LLM | litellm | Suporte a múltiplos modelos sem mudar código |
| Cache LLM | diskcache | Persiste entre reinicializações do container |
| Logging | structlog JSON | Auditável, sem PII, compatível com ELK futuro |

---

## Multi-escola (Futuro)

O campo `tenant_id` já existe em `AuditLogEntry` e nas tabelas SQL.
Para adicionar uma nova escola:
1. Gere um `tenant_id` único (ex: `"escola_goiania_001"`)
2. Filtre todas as queries por `tenant_id`
3. Não é necessário alterar schemas Pydantic nem contratos

## Multi-modelo (Futuro)

Para habilitar um novo modelo:
1. Adicione a `SupportedModel` enum em `contracts/data_models.py`
2. Adicione à lista `available` em `pedagogical_rules.json`
3. Altere `default` no JSON para ativar
4. Valide RAM disponível (ver notas por modelo no JSON)
