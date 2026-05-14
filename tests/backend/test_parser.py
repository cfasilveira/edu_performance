"""
tests/backend/test_parser.py
============================
Testes do parser de boletins escolares.
Agente 5 (QA) valida Agente 2 (Backend).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from src.io.gradebook_parser import GradebookParseError, parse_gradebook
from src.models.grade import hash_student_id

# ---------------------------------------------------------------------------
# Fixtures de dados de teste (NUNCA usar nomes/CPF reais)
# ---------------------------------------------------------------------------

def _make_csv(rows: list[dict]) -> bytes:
    """Gera CSV em memória a partir de lista de dicts."""
    if not rows:
        return b"aluno,nome,turma,disciplina,nota1,nota2,nota3,nota4\n"
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


VALID_ROWS = [
    {"aluno": "aluno_001", "nome": "Joao", "turma": "9A", "disciplina": "Matemática", "nota1": "7.25", "nota2": "7.0", "nota3": "8.0", "nota4": "6.0"},
    {"aluno": "aluno_002", "nome": "Maria", "turma": "9B", "disciplina": "Português", "nota1": "5,80", "nota2": "6.0", "nota3": "6.5", "nota4": "5.5"},
    {"aluno": "aluno_003", "nome": "Pedro", "turma": "8A", "disciplina": "Ciências", "nota1": "9.10", "nota2": "9.0", "nota3": "8.5", "nota4": "9.5"},
]


# ---------------------------------------------------------------------------
# Testes: parsing válido
# ---------------------------------------------------------------------------

class TestParseValid:
    def test_returns_grade_records(self):
        data = _make_csv(VALID_ROWS)
        records = parse_gradebook(data, period="2024-T1", file_extension="csv")
        assert len(records) == 12

    def test_student_id_is_hashed(self):
        data = _make_csv(VALID_ROWS)
        records = parse_gradebook(data, period="2024-T1", file_extension="csv")
        for r in records:
            assert len(r.student_hash) == 12
            assert "aluno_001" not in r.student_hash  # nunca ID raw

    def test_comma_decimal_normalized(self):
        """'58,0' deve ser convertido para 58.0 sem erro."""
        data = _make_csv(VALID_ROWS)
        records = parse_gradebook(data, period="2024-T1", file_extension="csv")
        notas = [r.grade for r in records]
        assert 5.8 in notas

    def test_period_propagated(self):
        data = _make_csv(VALID_ROWS)
        records = parse_gradebook(data, period="2024-T1", file_extension="csv")
        assert all(r.period == "2024-T1" for r in records)

    def test_performance_1000_rows(self):
        """Parsing de 1000 registros deve completar em < 2s (NVMe)."""
        import time
        rows = [
            {"aluno": f"aluno_{i:04d}", "turma": "9A", "disciplina": "Matemática",
             "nota1": str((50 + (i % 50)) / 10), "nota2": "6.0", "nota3": "7.0", "nota4": "8.0"}
            for i in range(1000)
        ]
        data = _make_csv(rows)
        start = time.monotonic()
        records = parse_gradebook(data, period="2024-T1", file_extension="csv")
        elapsed = time.monotonic() - start
        assert len(records) == 4000
        assert elapsed < 2.0, f"Parsing de 1000 registros levou {elapsed:.2f}s (limite: 2s)"


# ---------------------------------------------------------------------------
# Testes: dados inválidos / edge cases
# ---------------------------------------------------------------------------

class TestParseEdgeCases:
    def test_empty_file_raises(self):
        with pytest.raises(GradebookParseError, match="Nenhum registro válido"):
            parse_gradebook(b"aluno,nome,turma,disciplina,nota1,nota2,nota3,nota4\n", period="2024-T1", file_extension="csv")

    def test_missing_required_column_raises(self):
        data = b"aluno,turma,nota1,nota2,nota3,nota4\n001,9A,7.2,7.0,8.0,6.0\n"
        with pytest.raises(GradebookParseError, match="disciplina"):
            parse_gradebook(data, period="2024-T1", file_extension="csv")

    def test_invalid_extension_raises(self):
        with pytest.raises(GradebookParseError, match="Extensão não permitida"):
            parse_gradebook(b"", period="2024-T1", file_extension="exe")

    def test_empty_period_raises(self):
        data = _make_csv(VALID_ROWS)
        with pytest.raises(GradebookParseError, match="period"):
            parse_gradebook(data, period="", file_extension="csv")

    def test_invalid_subject_skipped_with_log(self):
        """Linha com disciplina inválida é pulada, não quebra o parse."""
        rows = VALID_ROWS + [
            {"aluno": "aluno_099", "turma": "9A", "disciplina": "XyzInvalido", "nota1": "7.0", "nota2": "7.0", "nota3": "7.0", "nota4": "7.0"}
        ]
        data = _make_csv(rows)
        records = parse_gradebook(data, period="2024-T1", file_extension="csv")
        assert len(records) == 12  # linha inválida pulada

    def test_file_too_large_raises(self):
        large = b"a" * (101 * 1024 * 1024)  # 101 MB
        with pytest.raises(GradebookParseError, match="grande"):
            parse_gradebook(large, period="2024-T1", file_extension="csv")


# ---------------------------------------------------------------------------
# Testes: segurança
# ---------------------------------------------------------------------------

class TestParseSecurity:
    def test_csv_injection_equals_raises(self):
        data = b"aluno,turma,disciplina,nota1,nota2,nota3,nota4\n=cmd|' /C calc',9A,Matematica,7.2,7.0,8.0,6.0\n"
        with pytest.raises(GradebookParseError, match="injection"):
            parse_gradebook(data, period="2024-T1", file_extension="csv")

    def test_csv_injection_plus_raises(self):
        data = b"aluno,turma,disciplina,nota1,nota2,nota3,nota4\n+malicious,9A,Matematica,7.2,7.0,8.0,6.0\n"
        with pytest.raises(GradebookParseError, match="injection"):
            parse_gradebook(data, period="2024-T1", file_extension="csv")

    def test_path_traversal_raises(self):
        evil_path = Path("/tmp/../../etc/passwd")
        with pytest.raises((GradebookParseError, FileNotFoundError)):
            parse_gradebook(evil_path, period="2024-T1")

    def test_student_pii_not_in_hash(self):
        """Hash não deve ser reversível para o nome do aluno."""
        h = hash_student_id("joao.silva.secreto@escola.edu")
        assert "joao" not in h
        assert "silva" not in h
        assert len(h) == 12
