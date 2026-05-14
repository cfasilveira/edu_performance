"""
src/models/grade.py
===================
Modelos de dados e helpers analíticos para notas e desempenho.
Agente 2 — Backend & Dados.

Re-exporta os tipos canônicos de /contracts/data_models.py e adiciona
helpers de análise que não pertencem ao contrato central.
"""

from __future__ import annotations

import hashlib
import re
from statistics import mean, stdev
from typing import Final

import structlog

from contracts.data_models import (
    AuditLogEntry,
    GradeRecord,
    GroupingResult,
    PerformanceLevel,
    StudentProfile,
    SubjectEnum,
    SupportedModel,
)

__all__ = [
    # Re-exports do contrato
    "GradeRecord",
    "StudentProfile",
    "GroupingResult",
    "PerformanceLevel",
    "SubjectEnum",
    "SupportedModel",
    "AuditLogEntry",
    # Helpers locais
    "hash_student_id",
    "sanitize_text_input",
    "compute_class_statistics",
    "PASSING_THRESHOLD",
    "AT_RISK_THRESHOLD",
    "EXCELLENCE_THRESHOLD",
]

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes — sempre sincronizadas com pedagogical_rules.json
# ---------------------------------------------------------------------------
PASSING_THRESHOLD: Final[float] = 6.0
AT_RISK_THRESHOLD: Final[float] = 5.0
EXCELLENCE_THRESHOLD: Final[float] = 8.5


# ---------------------------------------------------------------------------
# Helpers de segurança
# ---------------------------------------------------------------------------

def hash_student_id(student_id: str) -> str:
    """Pseudonimização LGPD: SHA-256[:12] do identificador do aluno.

    Args:
        student_id: Identificador original do aluno (qualquer string).

    Returns:
        String hexadecimal de 12 caracteres — nunca reversível.

    Example:
        >>> hash_student_id("joao.silva@escola.edu")
        'a3f1b2c4d5e6'
    """
    if not student_id:
        raise ValueError("student_id não pode ser vazio")
    return hashlib.sha256(student_id.strip().encode("utf-8")).hexdigest()[:12]


_SAFE_TEXT_RE: Final = re.compile(
    r"[^\w\s\-\.,:;!?áéíóúãõâêôçÁÉÍÓÚÃÕÂÊÔÇ]"
)


def sanitize_text_input(raw: str, max_length: int = 500) -> str:
    """Remove caracteres não permitidos e trunca o input do usuário.

    Proteção primária contra prompt injection e XSS.

    Args:
        raw: String bruta do usuário.
        max_length: Tamanho máximo permitido após sanitização.

    Returns:
        String sanitizada e truncada.

    Example:
        >>> sanitize_text_input("Olá! <script>alert(1)</script>")
        'Olá!'
    """
    if not isinstance(raw, str):
        raise TypeError(f"Esperado str, recebeu {type(raw).__name__}")
    sanitized = _SAFE_TEXT_RE.sub("", raw).strip()
    if len(sanitized) > max_length:
        log.warning("input_truncado", original_len=len(sanitized), max_len=max_length)
        sanitized = sanitized[:max_length]
    return sanitized


# ---------------------------------------------------------------------------
# Análise estatística de turma
# ---------------------------------------------------------------------------

def compute_class_statistics(
    records: list[GradeRecord],
) -> dict[str, dict[str, float]]:
    """Calcula estatísticas de desempenho por disciplina para uma lista de notas.

    Não contém PII — opera apenas em GradeRecord (já pseudonimizados).

    Args:
        records: Lista de notas validadas pelo schema Pydantic.

    Returns:
        Dicionário {subject_value: {mean, stdev, min, max, at_risk_pct}}.

    Example:
        >>> stats = compute_class_statistics(records)
        >>> stats["Matemática"]["mean"]
        62.5

    Edge cases:
        - Lista vazia → retorna {}
        - Disciplina com 1 aluno → stdev = 0.0
        - Todos abaixo do threshold → at_risk_pct = 100.0
    """
    if not records:
        log.warning("compute_class_statistics_empty_input")
        return {}

    by_subject: dict[str, list[float]] = {}
    for r in records:
        by_subject.setdefault(r.subject.value, []).append(r.grade)

    result: dict[str, dict[str, float]] = {}
    for subject, grades in by_subject.items():
        at_risk = sum(1 for g in grades if g < PASSING_THRESHOLD)
        result[subject] = {
            "mean": round(mean(grades), 2),
            "stdev": round(stdev(grades), 2) if len(grades) > 1 else 0.0,
            "min": min(grades),
            "max": max(grades),
            "count": float(len(grades)),
            "at_risk_pct": round(at_risk / len(grades) * 100, 1),
        }

    log.info(
        "class_statistics_computed",
        subjects=list(result.keys()),
        total_records=len(records),
    )
    return result
