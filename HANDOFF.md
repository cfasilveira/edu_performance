# 🤝 HANDOFF DOCUMENT — Agente [NOME DO AGENTE]

| Campo | Valor |
|-------|-------|
| **Agente Responsável** | [Ex: Agente 2 - Backend] |
| **Versão do Módulo** | `v0.1.0` |
| **Data/Hora** | `YYYY-MM-DD HH:MM` |
| **Status** | `✅ Aprovado` / `⚠️ Aprovado com ressalvas` / `❌ Rejeitado` |
| **Branch de Entrega** | `feat/[nome-do-modulo]` |
| **Commit Hash** | `git rev-parse HEAD` |

---

## 📦 1. Entregas Realizadas

- [ ] Arquivos criados/modificados:
  - `src/...`
  - `tests/...`
- [ ] Contratos atualizados em `/contracts/`: `[ ] Sim` / `[x] Não`
- [ ] Documentação interna (`docs/`): `[ ] Sim` / `[x] Não`

---

## 🧪 2. Resultados de Testes

| Métrica | Valor | Limiar Mínimo | Status |
|---------|-------|---------------|--------|
| Cobertura (`pytest-cov`) | `XX%` | `≥ 85%` | `[ ] OK` / `[ ] FAIL` |
| Testes de Segurança (OWASP) | `XX/XX` | `100%` | `[ ] OK` / `[ ] FAIL` |
| Testes de Performance (NVMe) | `XXs` | `≤ 2s` (parse 1k rows) | `[ ] OK` / `[ ] FAIL` |
| Validação de Contratos (`scripts/validate_contracts.py`) | `[ ] Pass` / `[ ] Fail` | `Pass` | `[ ] OK` |

**Comandos executados:**
```bash
uv run pytest tests/ -v --cov=src --cov-report=term-missing
python scripts/validate_contracts.py
```

---

## 🔐 3. Conformidade LGPD

- [ ] Nenhum PII (nome, CPF, endereço) nos logs
- [ ] Pseudonimização ativa: `GradeRecord.hash_student_id()` aplicado
- [ ] `AuditLogEntry` gerada para toda ação relevante (com `approved_by` + `timestamp`)
- [ ] `.env` não commitado (`git log --all -- .env` → vazio)

---

## ⚠️ 4. Ressalvas & Débitos Técnicos

| Item | Severidade | Plano de Resolução |
|------|-----------|-------------------|
| [Descreva a ressalva] | `Alta / Média / Baixa` | [Como será resolvido] |

---

## 🔗 5. Dependências para o Próximo Agente

- [ ] Agente 6 (Integration) deve validar os schemas em `/contracts/` antes de merge
- [ ] Pré-requisitos do próximo agente: [liste arquivos/módulos que precisam existir]
- [ ] Variáveis de ambiente necessárias (apenas nomes, sem valores — ver `.env.example`):
  - `EDU_DB_URL`
  - `EDU_OLLAMA_HOST`

---

*Gerado por: [Agente X] | Template versão: 1.1.0*
