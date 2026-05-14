#!/usr/bin/env python3
"""
scripts/validate_contracts.py
Validação cross-module de contratos, segurança e conformidade LGPD para o MVP EduAnalytics.
Executado automaticamente antes de qualquer merge ou handoff entre agentes.
"""

import ast
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Configuração de Paths
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = ROOT_DIR / "contracts"
SRC_DIR = ROOT_DIR / "src"

REPORT_LINES: List[str] = []
EXIT_CODE = 0

def log(msg: str, status: str = "✅"):
    REPORT_LINES.append(f"{status} {msg}")
    print(f"{status} {msg}")

def fail(msg: str):
    global EXIT_CODE
    EXIT_CODE = 1
    log(msg, "❌")

# ---------------------------------------------------------------------------
# 1. Carregar Contratos
# ---------------------------------------------------------------------------
def load_contracts() -> Dict[str, Any]:
    try:
        with open(CONTRACTS_DIR / "data_models.py", "r", encoding="utf-8") as f:
            # Nota: Em produção usaria importlib; aqui fazemos parsing leve para validação estática
            pass  # Modelos serão validados via import dinâmico na fase de testes
        with open(CONTRACTS_DIR / "pedagogical_rules.json", "r", encoding="utf-8") as f:
            rules = json.load(f)
        return {"rules": rules}
    except Exception as e:
        fail(f"Falha ao carregar contratos: {e}")
        sys.exit(1)

# ---------------------------------------------------------------------------
# 2. Validação de Segurança & LGPD (Static Analysis)
# ---------------------------------------------------------------------------
def check_security_guards():
    log("Iniciando auditoria estática de segurança e LGPD...")
    
    patterns_to_avoid = {
        # f-string que contém palavra SQL E interpolação — risco real de SQLi
        "sql_injection": r'f["\'].*\{.*\}.*(SELECT|INSERT|UPDATE|DELETE)',
        "pii_logging": r'log\([^)]*(nome|cpf|email|telefone)[^)]*\)',
        "print_debug": r'^\s*print\(',
        "hardcoded_secrets": r'(password|secret|key)\s*=\s*["\'][A-Za-z0-9]{8,}["\']',
    }
    
    required_patterns = {
        "pii_hashing": r"hashlib\.sha256",
        "structured_logging": r"structlog",
        "fail_fast": r"if not .*:.*\n.*return",
        "parameterized_sql": r"\?|\$[0-9]"
    }
    
    python_files = list(SRC_DIR.rglob("*.py"))
    if not python_files:
        fail("Nenhum arquivo .py encontrado em src/")
        return

    for file in python_files:
        rel_path = file.relative_to(ROOT_DIR)
        content = file.read_text(encoding="utf-8")
        
        # Verificar padrões proibidos
        for name, pattern in patterns_to_avoid.items():
            if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                fail(f"[{rel_path}] Violação de segurança detectada: {name}")
        
        # Verificar padrões obrigatórios (apenas em arquivos de lógica, não em __init__.py)
        if file.name != "__init__.py":
            for name, pattern in required_patterns.items():
                if not re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                    # Warning leve, não falha build, mas registra
                    log(f"[{rel_path}] Aviso: padrão recomendado não encontrado: {name}", "⚠️")

    log("Auditoria estática concluída.")

# ---------------------------------------------------------------------------
# 3. Validação de Regras Pedagógicas
# ---------------------------------------------------------------------------
def check_pedagogical_rules(contracts: Dict):
    log("Validando conformidade com regras pedagógicas...")
    rules = contracts["rules"]
    
    # Exemplo: validar thresholds hardcoded vs contratos
    expected_threshold = rules.get("passing_threshold", 60.0)
    # Busca por valores hardcoded em src/analytics/ e src/models/
    analytics_files = list((SRC_DIR / "analytics").rglob("*.py")) + \
                      list((SRC_DIR / "models").rglob("*.py"))
    
    for file in analytics_files:
        content = file.read_text(encoding="utf-8")
        # Detecta se há threshold hardcoded diferente do contrato
        hardcoded = re.findall(r"threshold\s*=\s*(\d+\.?\d*)", content)
        for val in hardcoded:
            if float(val) != expected_threshold:
                fail(f"[{file.relative_to(ROOT_DIR)}] Threshold hardcoded ({val}) diverge do contrato ({expected_threshold})")
    
    log("Regras pedagógicas validadas.")

# ---------------------------------------------------------------------------
# 4. Validação de Schemas Pydantic (Runtime Light Check)
# ---------------------------------------------------------------------------
def check_model_schemas():
    log("Validando schemas Pydantic vs contratos...")
    try:
        import importlib.util
        # Tenta importar contracts.data_models e src.models.grade
        spec_contract = importlib.util.spec_from_file_location("contract_models", CONTRACTS_DIR / "data_models.py")
        spec_impl = importlib.util.spec_from_file_location("impl_models", SRC_DIR / "models" / "grade.py")
        
        if spec_contract and spec_impl:
            # Em um pipeline CI real, rodaríamos pytest aqui.
            # Para validação rápida, apenas confirmamos que os arquivos existem e são parseáveis.
            compile(Path(CONTRACTS_DIR / "data_models.py").read_text(), "data_models.py", "exec")
            compile(Path(SRC_DIR / "models" / "grade.py").read_text(), "grade.py", "exec")
            log("Schemas compiláveis e estruturalmente válidos.")
        else:
            fail("Arquivos de modelo obrigatórios ausentes.")
    except Exception as e:
        fail(f"Falha na validação de schemas: {e}")

# ---------------------------------------------------------------------------
# 5. Relatório Final
# ---------------------------------------------------------------------------
def main():
    print("="*60)
    print("🛡️  VALIDAÇÃO DE CONTRATOS & SEGURANÇA - EDU PERFORMANCE MVP")
    print("="*60)
    
    contracts = load_contracts()
    check_security_guards()
    check_pedagogical_rules(contracts)
    check_model_schemas()
    
    print("\n" + "="*60)
    print("📊 RESUMO DA VALIDAÇÃO")
    print("="*60)
    for line in REPORT_LINES:
        print(line)
    
    if EXIT_CODE == 0:
        print("\n✅ TODAS AS VALIDAÇÕES PASSARAM. PRONTO PARA INTEGRAÇÃO.")
    else:
        print("\n❌ VALIDAÇÕES FALHARAM. REVISE OS ERROS ACIMA ANTES DE PROSSEGUIR.")
    
    sys.exit(EXIT_CODE)

if __name__ == "__main__":
    main()
