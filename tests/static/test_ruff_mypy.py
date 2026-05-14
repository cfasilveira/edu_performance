"""
tests/static/test_ruff_mypy.py
================================
Testes de análise estática: ruff e mypy.
Agente 5 — QA & Segurança.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


class TestStaticAnalysis:
    def test_ruff_no_errors(self):
        """ruff check deve retornar 0 erros em src/."""
        result = subprocess.run(
            ["uv", "run", "ruff", "check", "src/", "--select=E,F,W,I"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, (
            f"ruff encontrou erros:\n{result.stdout}\n{result.stderr}"
        )

    def test_no_print_statements_in_src(self):
        """Nenhum print() deve existir em src/ (use structlog)."""
        import re
        violations = []
        for f in (ROOT / "src").rglob("*.py"):
            content = f.read_text(encoding="utf-8")
            for i, line in enumerate(content.splitlines(), 1):
                if re.match(r"^\s*print\(", line) and not line.strip().startswith("#"):
                    violations.append(f"{f.relative_to(ROOT)}:{i}: {line.strip()}")
        assert not violations, f"print() encontrado:\n" + "\n".join(violations)

    def test_no_hardcoded_passwords_in_src(self):
        """Nenhuma senha hardcoded deve existir em src/."""
        import re
        pattern = re.compile(r'(password|secret|key)\s*=\s*["\'][A-Za-z0-9]{8,}["\']', re.I)
        violations = []
        for f in (ROOT / "src").rglob("*.py"):
            content = f.read_text(encoding="utf-8")
            for i, line in enumerate(content.splitlines(), 1):
                if pattern.search(line):
                    violations.append(f"{f.relative_to(ROOT)}:{i}: {line.strip()}")
        assert not violations, f"Credenciais hardcoded:\n" + "\n".join(violations)

    def test_contracts_dir_has_required_files(self):
        """Contrato central deve ter data_models.py e pedagogical_rules.json."""
        contracts = ROOT / "contracts"
        assert (contracts / "data_models.py").exists(), "data_models.py ausente"
        assert (contracts / "pedagogical_rules.json").exists(), "pedagogical_rules.json ausente"

    def test_all_src_modules_have_all_defined(self):
        """Módulos públicos em src/ devem ter __all__ definido."""
        missing = []
        for f in (ROOT / "src").rglob("*.py"):
            if f.name == "__init__.py":
                continue
            content = f.read_text(encoding="utf-8")
            if "__all__" not in content:
                missing.append(str(f.relative_to(ROOT)))
        assert not missing, f"Módulos sem __all__:\n" + "\n".join(missing)
