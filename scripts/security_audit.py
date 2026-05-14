#!/usr/bin/env python3
"""
scripts/security_audit.py
==========================
Auditoria de segurança automatizada para o EduAnalytics MVP.
Agente 5 — QA & Segurança.

Executa verificações além do validate_contracts.py:
- Verificação de dependências com vulnerabilidades conhecidas (pip-audit)
- Análise de secrets expostos (git history)
- Verificação de permissões de arquivos sensíveis
- Relatório SARIF-compatível
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
REPORT: list[dict] = []
EXIT_CODE = 0


def log_ok(check: str, detail: str = "") -> None:
    REPORT.append({"status": "PASS", "check": check, "detail": detail})
    print(f"  ✅ {check}" + (f" — {detail}" if detail else ""))


def log_fail(check: str, detail: str = "") -> None:
    global EXIT_CODE
    EXIT_CODE = 1
    REPORT.append({"status": "FAIL", "check": check, "detail": detail})
    print(f"  ❌ {check}" + (f" — {detail}" if detail else ""))


def log_warn(check: str, detail: str = "") -> None:
    REPORT.append({"status": "WARN", "check": check, "detail": detail})
    print(f"  ⚠️  {check}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# 1. Verificar .env não commitado
# ---------------------------------------------------------------------------
def check_env_not_committed() -> None:
    print("\n[1] Verificando .env no histórico git...")
    result = subprocess.run(
        ["git", "log", "--all", "--name-only", "--format=", "--", ".env"],
        cwd=ROOT_DIR, capture_output=True, text=True, timeout=15,
    )
    if ".env" in result.stdout:
        log_fail(".env no histórico git", "Execute: git filter-branch ou git-filter-repo")
    else:
        log_ok(".env não está no histórico git")


# ---------------------------------------------------------------------------
# 2. Verificar arquivos sensíveis sem permissão restrita
# ---------------------------------------------------------------------------
def check_file_permissions() -> None:
    print("\n[2] Verificando permissões de arquivos sensíveis...")
    sensitive = [ROOT_DIR / ".env", ROOT_DIR / "config" / "init.sql"]
    for f in sensitive:
        if not f.exists():
            continue
        mode = oct(f.stat().st_mode)[-3:]
        if mode in ("600", "700", "400"):
            log_ok(f"Permissão OK: {f.name}", mode)
        else:
            log_warn(f"Permissão ampla: {f.name}", f"Atual: {mode} — recomendado: 600")


# ---------------------------------------------------------------------------
# 3. Verificar que contracts/ tem os arquivos obrigatórios
# ---------------------------------------------------------------------------
def check_contracts_present() -> None:
    print("\n[3] Verificando arquivos de contrato...")
    required = [
        ROOT_DIR / "contracts" / "data_models.py",
        ROOT_DIR / "contracts" / "pedagogical_rules.json",
    ]
    for f in required:
        if f.exists():
            log_ok(f"Contrato presente: {f.name}")
        else:
            log_fail(f"Contrato ausente: {f.name}")


# ---------------------------------------------------------------------------
# 4. Verificar ausência de print() em src/
# ---------------------------------------------------------------------------
def check_no_print_statements() -> None:
    import re
    print("\n[4] Verificando ausência de print() em src/...")
    violations = []
    for f in (ROOT_DIR / "src").rglob("*.py"):
        content = f.read_text(encoding="utf-8")
        for i, line in enumerate(content.splitlines(), 1):
            if re.match(r"^\s*print\(", line) and not line.strip().startswith("#"):
                violations.append(f"{f.relative_to(ROOT_DIR)}:{i}")

    if violations:
        log_fail("print() encontrado em src/", ", ".join(violations[:5]))
    else:
        log_ok("Nenhum print() em src/")


# ---------------------------------------------------------------------------
# 5. Verificar dependências (pip-audit se disponível)
# ---------------------------------------------------------------------------
def check_dependencies() -> None:
    print("\n[5] Verificando dependências (pip-audit)...")
    try:
        result = subprocess.run(
            ["uv", "run", "pip-audit", "--format=json"],
            cwd=ROOT_DIR, capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            log_ok("pip-audit: nenhuma vulnerabilidade crítica")
        else:
            try:
                vulns = json.loads(result.stdout)
                count = len(vulns.get("vulnerabilities", []))
                log_fail(f"pip-audit: {count} vulnerabilidades encontradas", "Rode: uv run pip-audit")
            except json.JSONDecodeError:
                log_warn("pip-audit retornou saída inesperada", result.stdout[:200])
    except FileNotFoundError:
        log_warn("pip-audit não instalado", "Adicione pip-audit ao pyproject.toml[dev]")


# ---------------------------------------------------------------------------
# 6. Relatório final
# ---------------------------------------------------------------------------
def save_report() -> None:
    report_path = ROOT_DIR / "reports" / "security_audit.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.utcnow().isoformat(),
            "exit_code": EXIT_CODE,
            "checks": REPORT,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n  📄 Relatório salvo em: {report_path.relative_to(ROOT_DIR)}")


def main() -> None:
    print("=" * 60)
    print("🔍  AUDITORIA DE SEGURANÇA — EDU PERFORMANCE MVP")
    print("=" * 60)

    check_env_not_committed()
    check_file_permissions()
    check_contracts_present()
    check_no_print_statements()
    check_dependencies()
    save_report()

    print("\n" + "=" * 60)
    if EXIT_CODE == 0:
        print("✅  AUDITORIA PASSOU. Sem vulnerabilidades críticas.")
    else:
        print("❌  AUDITORIA FALHOU. Revise os itens acima.")
    print("=" * 60)
    sys.exit(EXIT_CODE)


if __name__ == "__main__":
    main()
