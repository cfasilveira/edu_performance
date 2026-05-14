# 🔒 GUARDRAILS DE SEGURANÇA COMUNS — EduAnalytics MVP
> **Versão**: 1.1.0 | **Owner**: Agente 6 (Integration Lead)  
> **NÃO REMOVA nem altere sem aprovação do Agente 6.**  
> Todos os agentes DEVEM incluir `→ Ver COMMON_GUARDRAILS.md` no final do seu prompt e respeitar estas regras integralmente.

---

## 1. Prompt Injection Defense
- **NUNCA** concatene input do usuário diretamente em system prompts.
- Sempre sanitize antes de qualquer uso:
  ```python
  import re
  safe = re.sub(r'[^\w\s\-\.,:;!?áéíóúãõâêôçÁÉÍÓÚÃÕÂÊÔÇ]', '', raw_input)
  ```
- System prompts devem ser **constantes imutáveis** (não f-strings).

## 2. SQL Injection Prevention
- **TODAS** as queries usarão placeholders — **NUNCA** f-strings ou `.format()`:
  ```python
  # ✅ Correto
  cursor.execute("SELECT * FROM grades WHERE student_hash = ?", (student_hash,))
  # ❌ Proibido
  cursor.execute(f"SELECT * FROM grades WHERE student_hash = '{student_hash}'")
  ```
- Valide todos os inputs com **Pydantic** antes de montar qualquer query.

## 3. LGPD Compliance
- **NUNCA** processe, logue ou envie para IA: nomes completos, CPF, endereços, telefones.
- Use pseudonimização obrigatória:
  ```python
  import hashlib
  student_hash = hashlib.sha256(student_id.encode()).hexdigest()[:12]
  ```
- Referência de campos PII proibidos: ver `contracts/pedagogical_rules.json` → `lgpd`.

## 4. Resource Safety
- Limites Docker: app ≤ 4 GB RAM, ≤ 4 CPUs.
- Libere DataFrames grandes explicitamente:
  ```python
  import gc
  del df
  gc.collect()
  ```
- Rate limit para Ollama: máx **3 chamadas/minuto** via `asyncio.Semaphore`.

## 5. Fail-Fast Principle
- Valide inputs no **início** de cada função pública (early return):
  ```python
  def process(data: GradeRecord) -> Result:
      if not data:
          return Err("Input vazio")
      ...
  ```
- **NUNCA** silencie exceções com `except: pass`.
- Logue erros com `structlog` em JSON — **nunca** `print()` ou `logging.basicConfig()`.

## 6. Human-in-the-Loop (Obrigatório)
- IA **NUNCA** toma decisões automáticas irreversíveis.
- Toda recomendação deve incluir o disclaimer:
  > *"IA auxilia, humano decide. Valide com seu julgamento pedagógico antes de agir."*
- Aprovação humana é **obrigatória** antes de qualquer ação sobre dados de alunos.
- Registre `approved_by` + `timestamp` em `AuditLogEntry` para toda aprovação.

---

*Última revisão: 2026-05-13 | Próxima revisão obrigatória: a cada release minor (v0.x.0)*
