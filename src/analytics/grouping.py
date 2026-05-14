"""
src/analytics/grouping.py
=========================
Algoritmo de agrupamento cross-turma por dificuldades compartilhadas.
Agente 2 — Backend & Dados.

Estratégia:
- Constrói vetor de notas por disciplina para cada aluno
- Calcula similaridade coseno entre alunos
- Forma grupos com alunos de dificuldades similares (threshold ≥ 0.75)
- Respeita limites do contrato: 3 ≤ tamanho_grupo ≤ 15
"""

from __future__ import annotations

import gc
import math
import uuid
from collections import defaultdict
from typing import Final

import structlog

from contracts.data_models import GradeRecord, GroupingResult, SubjectEnum
from src.models.grade import PASSING_THRESHOLD

__all__ = ["group_students_by_weakness", "GroupingError"]

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes — sincronizadas com pedagogical_rules.json
# ---------------------------------------------------------------------------
MIN_GROUP_SIZE: Final[int] = 3
MAX_GROUP_SIZE: Final[int] = 15
SIMILARITY_THRESHOLD: Final[float] = 0.75

# Ordem canônica dos sujeitos para construção dos vetores
_SUBJECT_ORDER: Final[list[str]] = [s.value for s in SubjectEnum]


# ---------------------------------------------------------------------------
# Exceção de domínio
# ---------------------------------------------------------------------------

class GroupingError(Exception):
    """Erro no agrupamento — sem stack trace para o usuário."""


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _build_grade_vector(grades: list[GradeRecord]) -> list[float]:
    """Converte lista de notas em vetor normalizado por disciplina.

    Disciplinas ausentes recebem 100.0 (sem dificuldade conhecida).

    Args:
        grades: Notas de um único aluno.

    Returns:
        Vetor de floats com comprimento = len(SubjectEnum).
    """
    grade_map: dict[str, float] = {}
    for g in grades:
        # Mantém a nota mais baixa se houver duplicatas (pior caso)
        key = g.subject.value
        grade_map[key] = min(grade_map.get(key, 10.0), g.grade)
    return [grade_map.get(subj, 10.0) for subj in _SUBJECT_ORDER]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similaridade coseno entre dois vetores.

    Vetores idênticos → 1.0. Vetores ortogonais → 0.0.

    Args:
        a: Vetor de notas do aluno A.
        b: Vetor de notas do aluno B.

    Returns:
        Float entre 0.0 e 1.0.
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x ** 2 for x in a))
    norm_b = math.sqrt(sum(y ** 2 for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _shared_weaknesses(
    student_hashes: list[str],
    profiles: dict[str, list[GradeRecord]],
) -> list[SubjectEnum]:
    """Retorna disciplinas em que TODOS os alunos do grupo estão abaixo do limiar.

    Args:
        student_hashes: Hashes dos alunos do grupo.
        profiles: Mapeamento hash → lista de GradeRecord.

    Returns:
        Lista de SubjectEnum em que o grupo tem dificuldade compartilhada.
    """
    weakness_counts: dict[SubjectEnum, int] = defaultdict(int)
    for h in student_hashes:
        weak = {g.subject for g in profiles.get(h, []) if g.grade < PASSING_THRESHOLD}
        for w in weak:
            weakness_counts[w] += 1
            
    # Include subjects where at least 50% of the group is weak
    threshold = len(student_hashes) / 2.0
    shared = [subj for subj, count in weakness_counts.items() if count >= threshold]
    return sorted(shared, key=lambda s: s.value)


# ---------------------------------------------------------------------------
# Função principal (API pública)
# ---------------------------------------------------------------------------

def group_students_by_weakness(
    records: list[GradeRecord],
) -> list[GroupingResult]:
    """Agrupa alunos com dificuldades compartilhadas, ignorando turma (cross-class).

    Algoritmo:
    1. Agrega notas por aluno (student_hash)
    2. Filtra apenas alunos com ao menos 1 nota abaixo do limiar
    3. Calcula similaridade coseno entre pares
    4. Forma grupos gulosos: percorre alunos e junta quem tem sim ≥ threshold
    5. Filtra grupos fora do intervalo [MIN_GROUP_SIZE, MAX_GROUP_SIZE]

    Args:
        records: Lista de GradeRecord validados pelo parser.

    Returns:
        Lista de GroupingResult ordenada por similarity_score decrescente.

    Raises:
        GroupingError: Se records estiver vazio.

    Example:
        >>> groups = group_students_by_weakness(records)
        >>> groups[0].shared_weaknesses
        [<SubjectEnum.MATEMATICA: 'Matemática'>]

    Edge cases:
        - Todos os alunos aprovados → retorna []
        - Aluno com notas em apenas 1 disciplina → vetor parcial (resto = 100.0)
        - Menos de MIN_GROUP_SIZE alunos em risco → retorna []
    """
    # ── 1. Fail-fast ──────────────────────────────────────────────────────
    if not records:
        raise GroupingError("Lista de records vazia — não há dados para agrupar")

    # ── 2. Agregar notas por aluno ────────────────────────────────────────
    profiles: dict[str, list[GradeRecord]] = defaultdict(list)
    for r in records:
        profiles[r.student_hash].append(r)

    # ── 3. Filtrar alunos com ao menos 1 nota abaixo do limiar ────────────
    at_risk_hashes = [
        h for h, grades in profiles.items()
        if any(g.grade < PASSING_THRESHOLD for g in grades)
    ]

    log.info(
        "grouping_start",
        total_students=len(profiles),
        at_risk_students=len(at_risk_hashes),
    )

    if len(at_risk_hashes) < MIN_GROUP_SIZE:
        log.info("grouping_no_groups_possible", reason="insufficient_at_risk_students")
        return []

    # ── 4. Construir vetores ──────────────────────────────────────────────
    vectors: dict[str, list[float]] = {
        h: _build_grade_vector(profiles[h]) for h in at_risk_hashes
    }

    # ── 5. Agrupamento guloso com similaridade coseno ─────────────────────
    assigned: set[str] = set()
    groups: list[GroupingResult] = []

    for seed in at_risk_hashes:
        if seed in assigned:
            continue

        group_members = [seed]
        for candidate in at_risk_hashes:
            if candidate == seed or candidate in assigned:
                continue
            sim = _cosine_similarity(vectors[seed], vectors[candidate])
            if sim >= SIMILARITY_THRESHOLD:
                group_members.append(candidate)
            if len(group_members) >= MAX_GROUP_SIZE:
                break

        # ── 6. Respeita limites do contrato ───────────────────────────────
        if len(group_members) < MIN_GROUP_SIZE:
            continue

        # Calcula similaridade média do grupo
        sim_scores = [
            _cosine_similarity(vectors[seed], vectors[m])
            for m in group_members if m != seed
        ]
        avg_sim = sum(sim_scores) / len(sim_scores) if sim_scores else 1.0

        weaknesses = _shared_weaknesses(group_members, profiles)
        group_id = f"grp_{uuid.uuid4().hex[:8]}"

        result = GroupingResult(
            group_id=group_id,
            student_hashes=group_members,
            shared_weaknesses=weaknesses,
            similarity_score=round(avg_sim, 3),
        )
        groups.append(result)

        for m in group_members:
            assigned.add(m)

    # ── 7. Liberar memória ────────────────────────────────────────────────
    del vectors, profiles
    gc.collect()

    # ── 8. Ordenar por similaridade e retornar ────────────────────────────
    groups.sort(key=lambda g: g.similarity_score, reverse=True)

    log.info(
        "grouping_complete",
        groups_formed=len(groups),
        students_grouped=len(assigned),
        students_not_grouped=len(at_risk_hashes) - len(assigned),
    )
    return groups
