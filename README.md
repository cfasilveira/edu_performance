# 🎯 EduAnalytics MVP

> Sistema de análise de desempenho escolar com IA local, agrupamento cross-turma e auditoria pedagógica.  
> **Status**: `🟦 MVP em desenvolvimento` | **Licença**: `MIT` | **Python**: `3.12+`

## 🚀 Visão Geral
Detecta padrões de dificuldade em boletins escolares, agrupa alunos por sintomas compartilhados (ignorando turmas), otimiza recursos (horários/salas/professores) e gera planos de reforço com apoio de IA local (Ollama + Mistral). Todo o fluxo é auditável e LGPD-compliant.

## 🤖 Arquitetura Multi-Agente
Este projeto é desenvolvido por 6 agentes especializados que se comunicam via contratos:

| Agente | Responsabilidade | Diretório Principal |
|--------|-----------------|---------------------|
| 🔷 DevOps & Infra | Docker, redes, limites, segurança de infra | `docker-compose.yml`, `Dockerfile`, `config/` |
| 🟨 Backend & Dados | Parsing de boletins, modelos Pydantic, analytics | `src/io/`, `src/models/`, `src/analytics/` |
| 🟧 IA & Pedagogia | Integração Ollama, prompts seguros, fallbacks | `src/llm/`, `prompts/` |
| 🟥 UI & UX | Streamlit, gestão de estado, fluxo humano-no-loop | `src/ui/`, `src/ui/components/` |
| ⬛ QA & Segurança | Testes, LGPD, profiling, compliance | `tests/`, `ci/`, `scripts/` |
| ⚫ Integração (Lead) | Orquestração, contratos, release, docs | `/`, `docs/`, `HANDOFF.md` |

### 📜 Regras de Comportamento dos Agentes
1. **Contratos primeiro**: Leia `/contracts/` antes de codificar.
2. **Testes obrigatórios**: Nenhum `HANDOFF.md` sem `pytest -v --cov=src` verde.
3. **Segurança em camadas**: Sanitização → Schema → Query parametrizada → Guardrail de output.
4. **README é read-only**: Só o Agente 6 modifica este arquivo.
5. **Fail-fast + Early Return**: Valide inputs no início; retorne cedo em erros.

