"""
tests/load/test_concurrent_uploads.py
=======================================
Testes de carga: uploads simultâneos e vazamento de memória.
Agente 5 — QA & Segurança.
"""

from __future__ import annotations

import csv
import io
import tracemalloc
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from src.io.gradebook_parser import parse_gradebook


def _make_csv(n: int = 100) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["aluno", "nome", "turma", "disciplina", "nota1", "nota2", "nota3", "nota4"])
    w.writeheader()
    for i in range(n):
        w.writerow({
            "aluno": f"aluno_{i:04d}", "nome": "Mock", "turma": "9A",
            "disciplina": "Matemática", 
            "nota1": str((60 + i % 40) / 10.0),
            "nota2": "7.0", "nota3": "8.0", "nota4": "9.0"
        })
    return buf.getvalue().encode("utf-8")


class TestConcurrentUploads:
    def test_10_concurrent_uploads_succeed(self):
        """10 uploads simultâneos devem todos completar com sucesso."""
        csv_data = _make_csv(50)
        results = []
        errors = []

        def upload(i: int):
            try:
                return parse_gradebook(csv_data, period="2024-T1", file_extension="csv")
            except Exception as e:
                return e

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(upload, i) for i in range(10)]
            for f in as_completed(futures):
                result = f.result()
                if isinstance(result, Exception):
                    errors.append(result)
                else:
                    results.append(result)

        assert len(errors) == 0, f"Erros em uploads simultâneos: {errors}"
        assert len(results) == 10
        assert all(len(r) == 50 for r in results)

    def test_no_memory_leak_after_uploads(self):
        """Memória liberada após processar múltiplos CSVs grandes."""
        tracemalloc.start()
        csv_data = _make_csv(500)

        for _ in range(5):
            parse_gradebook(csv_data, period="2024-T1", file_extension="csv")

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Pico de memória deve ser < 100 MB para 5 × 500 linhas
        peak_mb = peak / (1024 * 1024)
        assert peak_mb < 100, f"Pico de memória excessivo: {peak_mb:.1f} MB"

    def test_large_file_parsed_correctly(self):
        """CSV com 1000 linhas deve ser parseado sem erro."""
        csv_data = _make_csv(1000)
        records = parse_gradebook(csv_data, period="2024-T1", file_extension="csv")
        assert len(records) == 1000
