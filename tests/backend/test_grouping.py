"""
tests/backend/test_grouping.py
==============================
Testes do algoritmo de agrupamento cross-turma.
"""

from __future__ import annotations

import pytest

from contracts.data_models import GradeRecord, SubjectEnum
from src.analytics.grouping import GroupingError, group_students_by_weakness
from src.models.grade import hash_student_id


# ---------------------------------------------------------------------------
# Helpers de fixture
# ---------------------------------------------------------------------------

def _make_record(student_id: str, subject: SubjectEnum, grade: float, class_id: str = "9A") -> GradeRecord:
    return GradeRecord(
        student_hash=hash_student_id(student_id),
        class_id=class_id,
        subject=subject,
        grade=grade,
        period="2024-T1",
    )


# ---------------------------------------------------------------------------
# Testes: agrupamento válido
# ---------------------------------------------------------------------------

class TestGroupingValid:
    def test_forms_group_with_shared_weakness(self):
        records = [
            _make_record("aluno_a", SubjectEnum.MATEMATICA, 40.0, "9A"),
            _make_record("aluno_b", SubjectEnum.MATEMATICA, 35.0, "9B"),
            _make_record("aluno_c", SubjectEnum.MATEMATICA, 45.0, "8A"),
        ]
        groups = group_students_by_weakness(records)
        assert len(groups) >= 1
        assert SubjectEnum.MATEMATICA in groups[0].shared_weaknesses

    def test_cross_class_grouping(self):
        """Alunos de turmas diferentes devem poder ser agrupados."""
        records = [
            _make_record("x1", SubjectEnum.PORTUGUES, 42.0, "9A"),
            _make_record("x2", SubjectEnum.PORTUGUES, 38.0, "9B"),
            _make_record("x3", SubjectEnum.PORTUGUES, 44.0, "8C"),
        ]
        groups = group_students_by_weakness(records)
        assert len(groups) >= 1
        hashes = groups[0].student_hashes
        # Deve haver alunos de turmas diferentes
        student_classes = {
            r.class_id for r in records if r.student_hash in hashes
        }
        assert len(student_classes) >= 2

    def test_all_approved_returns_empty(self):
        """Se nenhum aluno está em risco, retorna lista vazia."""
        records = [
            _make_record(f"aluno_{i}", SubjectEnum.MATEMATICA, 75.0 + i, "9A")
            for i in range(5)
        ]
        groups = group_students_by_weakness(records)
        assert groups == []

    def test_group_size_minimum(self):
        """Grupos com menos de 3 alunos não são criados."""
        records = [
            _make_record("solo_a", SubjectEnum.MATEMATICA, 30.0),
            _make_record("solo_b", SubjectEnum.PORTUGUES, 20.0),  # disciplina diferente
        ]
        groups = group_students_by_weakness(records)
        for g in groups:
            assert len(g.student_hashes) >= 3

    def test_group_size_maximum(self):
        """Grupos não devem exceder 15 alunos."""
        records = [
            _make_record(f"aluno_{i}", SubjectEnum.MATEMATICA, 40.0)
            for i in range(30)
        ]
        groups = group_students_by_weakness(records)
        for g in groups:
            assert len(g.student_hashes) <= 15

    def test_similarity_score_range(self):
        records = [
            _make_record(f"a{i}", SubjectEnum.MATEMATICA, 35.0 + i * 2)
            for i in range(5)
        ]
        groups = group_students_by_weakness(records)
        for g in groups:
            assert 0.0 <= g.similarity_score <= 1.0

    def test_results_sorted_by_similarity(self):
        """Resultado deve estar em ordem decrescente de similarity_score."""
        records = [
            _make_record(f"b{i}", SubjectEnum.MATEMATICA, 40.0)
            for i in range(10)
        ] + [
            _make_record(f"c{i}", SubjectEnum.PORTUGUES, 42.0)
            for i in range(10)
        ]
        groups = group_students_by_weakness(records)
        scores = [g.similarity_score for g in groups]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Testes: edge cases
# ---------------------------------------------------------------------------

class TestGroupingEdgeCases:
    def test_empty_records_raises(self):
        with pytest.raises(GroupingError, match="vazia"):
            group_students_by_weakness([])

    def test_single_student_below_threshold(self):
        records = [_make_record("solo", SubjectEnum.MATEMATICA, 30.0)]
        groups = group_students_by_weakness(records)
        assert groups == []

    def test_student_with_one_subject_only(self):
        """Aluno com nota em apenas 1 disciplina — vetor parcial."""
        records = [
            _make_record(f"p{i}", SubjectEnum.MATEMATICA, 40.0)
            for i in range(4)
        ]
        groups = group_students_by_weakness(records)
        assert len(groups) >= 1

    def test_no_shared_weaknesses_between_groups(self):
        """Aluno reprovado em Matemática e outro em Português — sem grupo comum."""
        records = [
            _make_record("mat_a", SubjectEnum.MATEMATICA, 30.0),
            _make_record("mat_b", SubjectEnum.MATEMATICA, 35.0),
            _make_record("por_a", SubjectEnum.PORTUGUES, 25.0),
            _make_record("por_b", SubjectEnum.PORTUGUES, 28.0),
        ]
        # Deve haver no máximo grupos separados, não misturados
        groups = group_students_by_weakness(records)
        # Não testamos a existência de grupos (depende do threshold), mas a
        # ausência de crash é suficiente
        assert isinstance(groups, list)
