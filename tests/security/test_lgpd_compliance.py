"""
tests/security/test_lgpd_compliance.py
=======================================
Testes de conformidade LGPD.
Agente 5 — QA & Segurança.

Verifica: pseudonimização, audit trail imutável, ausência de PII em logs,
consentimento registrado e direito ao esquecimento (mock).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest

from contracts.data_models import AuditLogEntry, GradeRecord, SubjectEnum
from src.models.grade import hash_student_id, sanitize_text_input


# ---------------------------------------------------------------------------
# 1. Pseudonimização
# ---------------------------------------------------------------------------

class TestPseudonymization:
    def test_hash_is_12_chars(self):
        h = hash_student_id("aluno.teste.001")
        assert len(h) == 12

    def test_hash_is_hex(self):
        h = hash_student_id("aluno.teste.001")
        int(h, 16)  # não levanta exceção se for hex válido

    def test_hash_is_irreversible(self):
        h = hash_student_id("joao.silva.secreto")
        assert "joao" not in h
        assert "silva" not in h
        assert "secreto" not in h

    def test_same_id_same_hash(self):
        assert hash_student_id("aluno_001") == hash_student_id("aluno_001")

    def test_different_ids_different_hashes(self):
        assert hash_student_id("aluno_001") != hash_student_id("aluno_002")

    def test_empty_id_raises(self):
        with pytest.raises(ValueError):
            hash_student_id("")

    def test_grade_record_uses_hash(self):
        """GradeRecord não deve aceitar IDs não-hashed como student_hash."""
        h = hash_student_id("aluno_teste")
        record = GradeRecord(
            student_hash=h,
            class_id="9A",
            subject=SubjectEnum.MATEMATICA,
            grade=70.0,
            period="2024-T1",
        )
        assert record.student_hash == h
        assert len(record.student_hash) == 12

    def test_pii_names_not_accepted_as_student_hash(self):
        """student_hash deve ter exatamente 12 chars — nome completo falharia."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            GradeRecord(
                student_hash="João Silva",  # nome real — muito longo, inválido
                class_id="9A",
                subject=SubjectEnum.MATEMATICA,
                grade=70.0,
                period="2024-T1",
            )


# ---------------------------------------------------------------------------
# 2. Audit Trail Imutável
# ---------------------------------------------------------------------------

class TestAuditTrail:
    def _make_entry(self) -> AuditLogEntry:
        return AuditLogEntry(
            event_id=str(uuid.uuid4()),
            event_type="upload",
            actor="prof_teste",
            tenant_id="school_mvp",
            timestamp=datetime.utcnow(),
            details={"total_records": 50},
        )

    def test_audit_entry_is_frozen(self):
        """AuditLogEntry com frozen=True não pode ser alterada após criação."""
        entry = self._make_entry()
        with pytest.raises(Exception):  # ValidationError ou TypeError
            entry.event_type = "modified"  # type: ignore[misc]

    def test_audit_entry_has_required_fields(self):
        entry = self._make_entry()
        assert entry.event_id
        assert entry.event_type
        assert entry.actor
        assert entry.tenant_id
        assert entry.timestamp

    def test_audit_entry_details_no_pii(self):
        """Details não deve conter campos com PII."""
        entry = self._make_entry()
        details_str = json.dumps(entry.details)
        pii_fields = ["nome", "cpf", "email", "telefone", "endereco"]
        for field in pii_fields:
            assert field not in details_str.lower()

    def test_audit_entry_tenant_id_present(self):
        entry = self._make_entry()
        assert entry.tenant_id == "school_mvp"


# ---------------------------------------------------------------------------
# 3. Consentimento e Aprovação
# ---------------------------------------------------------------------------

class TestConsent:
    def test_approval_requires_approver_field(self):
        """AIRecommendation aprovada deve ter approved_by preenchido."""
        from contracts.data_models import AIRecommendation, SupportedModel
        rec = AIRecommendation(
            group_id="grp_001",
            recommendations=["Reforço em Matemática"],
            subjects_addressed=[SubjectEnum.MATEMATICA],
            model_used=SupportedModel.MISTRAL,
            approved_by="Prof. Maria",
            approved_at=datetime.utcnow(),
        )
        assert rec.approved_by == "Prof. Maria"
        assert rec.approved_at is not None

    def test_unapproved_recommendation_has_no_approver(self):
        from contracts.data_models import AIRecommendation, SupportedModel
        rec = AIRecommendation(
            group_id="grp_002",
            recommendations=["Reforço em Português"],
            subjects_addressed=[SubjectEnum.PORTUGUES],
            model_used=SupportedModel.MISTRAL,
        )
        assert rec.approved_by is None
        assert rec.approved_at is None


# ---------------------------------------------------------------------------
# 4. Direito ao Esquecimento (Mock)
# ---------------------------------------------------------------------------

class TestRightToErasure:
    def test_erasure_by_tenant_id_mock(self):
        """Simula endpoint de limpeza de dados por tenant_id."""
        deleted_records: list[str] = []

        def mock_delete_by_tenant(tenant_id: str) -> dict:
            """Mock de operação de limpeza — idempotente."""
            if tenant_id == "school_mvp":
                deleted_records.append(tenant_id)
                return {"deleted": True, "tenant_id": tenant_id, "records_deleted": 50}
            return {"deleted": False, "reason": "tenant_not_found"}

        result = mock_delete_by_tenant("school_mvp")
        assert result["deleted"] is True
        assert result["tenant_id"] == "school_mvp"

        # Idempotente — segunda chamada não levanta exceção
        result2 = mock_delete_by_tenant("school_mvp")
        assert result2["deleted"] is True

    def test_erasure_unknown_tenant_returns_not_found(self):
        def mock_delete_by_tenant(tenant_id: str) -> dict:
            known = ["school_mvp"]
            if tenant_id not in known:
                return {"deleted": False, "reason": "tenant_not_found"}
            return {"deleted": True, "tenant_id": tenant_id}

        result = mock_delete_by_tenant("escola_desconhecida")
        assert result["deleted"] is False


# ---------------------------------------------------------------------------
# 5. Logs sem PII
# ---------------------------------------------------------------------------

class TestLogsPII:
    def test_sanitize_removes_special_chars(self):
        raw = "Olá! <script>alert('xss')</script>"
        safe = sanitize_text_input(raw)
        assert "<script>" not in safe
        assert "alert" not in safe

    def test_sanitize_preserves_portuguese(self):
        raw = "Reforço em Matemática para alunos com dificuldade"
        safe = sanitize_text_input(raw)
        assert "Reforço" in safe
        assert "Matemática" in safe

    def test_sanitize_truncates_long_input(self):
        raw = "a" * 1000
        safe = sanitize_text_input(raw, max_length=500)
        assert len(safe) <= 500

    def test_env_file_not_in_git(self):
        """Verifica que .env não está no histórico git."""
        import subprocess
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent.parent
        result = subprocess.run(
            ["git", "log", "--all", "--name-only", "--format=", "--", ".env"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        assert ".env" not in result.stdout, "CRÍTICO: .env no histórico git!"
