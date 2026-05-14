"""
tests/integration/test_full_pipeline.py
========================================
Smoke test end-to-end do pipeline completo.
Agente 6 — Integração & Release.

Valida o fluxo: Upload → Agrupamento → IA (mock) → Aprovação → Auditoria
Sem containers — usa mocks para Ollama.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import time
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from contracts.data_models import (
    AIRecommendation,
    AuditLogEntry,
    GradeRecord,
    GroupingResult,
    SubjectEnum,
    SupportedModel,
)
from src.analytics.grouping import group_students_by_weakness
from src.io.gradebook_parser import parse_gradebook
from src.llm.advisor import PedagogicalAdvisor
from src.models.grade import hash_student_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_csv_bytes(n_students: int = 30) -> bytes:
    """Gera boletim mock com n_students alunos e disciplinas variadas."""
    subjects = ["Matemática", "Português", "Ciências", "História", "Geografia"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["aluno", "nome", "turma", "disciplina", "nota1", "nota2", "nota3", "nota4"])
    writer.writeheader()

    for i in range(n_students):
        turma = "9A" if i < 15 else "9B"
        for j, subj in enumerate(subjects):
            # Primeiros 10 alunos têm dificuldade em Matemática
            nota = 40.0 + (i * 2 % 30) if (i < 10 and subj == "Matemática") else 70.0 + (i % 20)
            nota = min(nota, 100.0)
            writer.writerow({
                "aluno": f"aluno_pipe_{i:03d}",
                "nome": "Mock",
                "turma": turma,
                "disciplina": subj,
                "nota1": f"{nota:.1f}",
                "nota2": f"{nota:.1f}",
                "nota3": f"{nota:.1f}",
                "nota4": f"{nota:.1f}",
            })

    return buf.getvalue().encode("utf-8")


MOCK_LLM_RESPONSE = {
    "recommendations": [
        "Criar grupo de reforço em Matemática às terças-feiras",
        "Utilizar jogos educativos para fixação de conceitos",
        "Agendar atendimento individualizado quinzenal",
    ],
    "subjects_addressed": ["Matemática"],
    "disclaimer": "IA auxilia, humano decide. Valide com seu julgamento pedagógico antes de agir.",
}


# ---------------------------------------------------------------------------
# Pipeline completo
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_upload_to_records(self):
        """Passo 1: Upload → GradeRecord válidos."""
        csv_bytes = _make_csv_bytes(30)
        records = parse_gradebook(csv_bytes, period="2024-T1", file_extension="csv")

        assert len(records) > 0
        assert all(isinstance(r, GradeRecord) for r in records)
        assert all(len(r.student_hash) == 12 for r in records)
        assert all(r.period == "2024-T1" for r in records)

    def test_records_to_groups(self):
        """Passo 2: GradeRecord → GroupingResult cross-turma."""
        csv_bytes = _make_csv_bytes(30)
        records = parse_gradebook(csv_bytes, period="2024-T1", file_extension="csv")
        groups = group_students_by_weakness(records)

        assert isinstance(groups, list)
        for g in groups:
            assert isinstance(g, GroupingResult)
            assert 3 <= len(g.student_hashes) <= 15
            assert 0.0 <= g.similarity_score <= 1.0

    def test_groups_to_ai_recommendation(self):
        """Passo 3: GroupingResult → AIRecommendation (com mock do Ollama)."""
        csv_bytes = _make_csv_bytes(30)
        records = parse_gradebook(csv_bytes, period="2024-T1", file_extension="csv")
        groups = group_students_by_weakness(records)

        if not groups:
            pytest.skip("Nenhum grupo gerado com estes dados mock")

        target_group = groups[0]
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(MOCK_LLM_RESPONSE)

        with patch("litellm.completion", return_value=mock_response):
            advisor = PedagogicalAdvisor()
            rec = asyncio.run(advisor.recommend(target_group))
            advisor.close()

        assert isinstance(rec, AIRecommendation)
        assert rec.group_id == target_group.group_id
        assert len(rec.recommendations) >= 1
        assert rec.disclaimer
        assert rec.model_used == SupportedModel.MISTRAL

    def test_ai_recommendation_approval(self):
        """Passo 4: Aprovação humana registrada em AuditLogEntry."""
        rec = AIRecommendation(
            group_id="grp_integration_test",
            recommendations=["Reforço em Matemática"],
            subjects_addressed=[SubjectEnum.MATEMATICA],
            model_used=SupportedModel.MISTRAL,
            approved_by="Prof. Integração",
            approved_at=datetime.utcnow(),
        )

        audit_entry = AuditLogEntry(
            event_id=str(uuid.uuid4()),
            event_type="ai_recommendation_approved",
            actor="Prof. Integração",
            tenant_id="school_mvp",
            timestamp=datetime.utcnow(),
            details={
                "group_id": rec.group_id,
                "model_used": rec.model_used.value,
            },
        )

        assert audit_entry.event_type == "ai_recommendation_approved"
        assert audit_entry.actor == "Prof. Integração"
        assert "group_id" in audit_entry.details
        # AuditLogEntry é imutável (frozen=True)
        with pytest.raises(Exception):
            audit_entry.actor = "modificado"  # type: ignore[misc]

    def test_full_pipeline_no_pii_leak(self):
        """Pipeline completo não deve vazar PII em nenhum estágio."""
        csv_bytes = _make_csv_bytes(20)
        records = parse_gradebook(csv_bytes, period="2024-T1", file_extension="csv")

        # Verificar que nenhum student_hash contém o ID original
        for i in range(20):
            original_id = f"aluno_pipe_{i:03d}"
            for r in records:
                assert original_id not in r.student_hash

        groups = group_students_by_weakness(records)
        for g in groups:
            for h in g.student_hashes:
                # Hashes não contêm "aluno" ou "pipe"
                assert "aluno" not in h
                assert "pipe" not in h

    def test_full_pipeline_performance(self):
        """Pipeline completo (sem IA) deve completar em < 5 minutos."""
        start = time.monotonic()

        csv_bytes = _make_csv_bytes(100)
        records = parse_gradebook(csv_bytes, period="2024-T1", file_extension="csv")
        groups = group_students_by_weakness(records)

        elapsed = time.monotonic() - start
        assert elapsed < 30.0, f"Pipeline (sem IA) levou {elapsed:.1f}s (limite: 30s)"
        assert len(records) > 0

    def test_contracts_cross_module_compatible(self):
        """Schemas dos módulos são compatíveis com os contratos centrais."""
        # GradeRecord do parser é o mesmo do contrato
        from contracts.data_models import GradeRecord as ContractGrade
        from src.models.grade import GradeRecord as SrcGrade
        assert ContractGrade is SrcGrade

        # GroupingResult do analytics é o mesmo do contrato
        from contracts.data_models import GroupingResult as ContractGroup
        from src.analytics.grouping import GroupingResult as AnalyticsGroup
        assert ContractGroup is AnalyticsGroup


# ---------------------------------------------------------------------------
# Validação de contratos cross-module
# ---------------------------------------------------------------------------

class TestContractValidation:
    def test_pedagogical_rules_json_valid(self):
        """pedagogical_rules.json deve ser JSON válido e ter campos obrigatórios."""
        from pathlib import Path
        rules_path = Path(__file__).resolve().parent.parent.parent / "contracts" / "pedagogical_rules.json"
        assert rules_path.exists()

        with open(rules_path, encoding="utf-8") as f:
            rules = json.load(f)

        assert "grading" in rules
        assert "passing_threshold" in rules["grading"]
        assert "models" in rules
        assert "default" in rules["models"]
        assert "lgpd" in rules

    def test_supported_model_matches_rules(self):
        """Modelo padrão no JSON deve existir em SupportedModel enum."""
        from pathlib import Path
        rules_path = Path(__file__).resolve().parent.parent.parent / "contracts" / "pedagogical_rules.json"
        with open(rules_path, encoding="utf-8") as f:
            rules = json.load(f)

        default_model = rules["models"]["default"]
        assert default_model in [m.value for m in SupportedModel]

    def test_passing_threshold_matches_code(self):
        """Threshold do JSON deve bater com a constante no código."""
        from pathlib import Path
        rules_path = Path(__file__).resolve().parent.parent.parent / "contracts" / "pedagogical_rules.json"
        with open(rules_path, encoding="utf-8") as f:
            rules = json.load(f)

        from src.models.grade import PASSING_THRESHOLD
        assert rules["grading"]["passing_threshold"] == PASSING_THRESHOLD
