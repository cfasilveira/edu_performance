"""
contracts/data_models.py
========================
Contrato central de modelos de dados do EduAnalytics MVP.
NÃO modifique sem validação do Agente 6 (integration).

Todos os agentes DEVEM importar schemas deste módulo.
Versão: 1.1.0

Decisões de arquitetura:
- tenant_id: MVP opera com escola única ("school_mvp"). Campo já presente em
  AuditLogEntry para migração futura zero-downtime (adicionar escola = novo tenant_id).
- SupportedModel: Abstração para LLMs via Ollama. Padrão = mistral. Novos modelos
  são adicionados aqui e em pedagogical_rules.json["models"] sem quebrar contratos.
- Deploy: MVP local (Ubuntu 24.04 + Docker). TLS e CI externo são opcionais.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "SubjectEnum",
    "PerformanceLevel",
    "SupportedModel",
    "GradeRecord",
    "StudentProfile",
    "TeacherProfile",
    "ClassProfile",
    "GroupingResult",
    "AIRecommendation",
    "HandoffStatus",
    "AuditLogEntry",
]

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SubjectEnum(str, Enum):
    MATEMATICA = "Matemática"
    PORTUGUES = "Português"
    CIENCIAS = "Ciências"
    HISTORIA = "História"
    GEOGRAFIA = "Geografia"
    ARTES = "Artes"
    EDUCACAO_FISICA = "Educação Física"
    INGLES = "Língua Inglesa"
    INFORMATICA = "Informática"


class PerformanceLevel(str, Enum):
    EXCELLENCE = "excellence"   # >= 85
    PASSING = "passing"         # >= 60
    AT_RISK = "at_risk"         # >= 50
    FAILING = "failing"         # < 50


class SupportedModel(str, Enum):
    """Modelos LLM suportados via Ollama.

    Adicione novos modelos aqui conforme forem testados e aprovados.
    O campo `default` em pedagogical_rules.json["models"] define qual usar.
    """
    MISTRAL = "mistral"              # padrão MVP — 7.1 GB, CPU-only
    LLAMA3 = "llama3"                # futuro — 8B, requer validação de RAM
    QWEN2 = "qwen2"                  # futuro — 7B, multilingual
    GEMMA2 = "gemma2"                # futuro — 9B, Google
    CUSTOM = "custom"                # modelos fine-tuned locais


class HandoffStatus(str, Enum):
    APPROVED = "approved"
    APPROVED_WITH_CAVEATS = "approved_with_caveats"
    REJECTED = "rejected"
    PENDING = "pending"


# ---------------------------------------------------------------------------
# Core Data Models
# ---------------------------------------------------------------------------

class GradeRecord(BaseModel):
    """Nota individual de um aluno em uma disciplina."""

    model_config = ConfigDict(strict=True, frozen=False)

    # PII NEVER stored raw — use student_hash
    student_hash: Annotated[str, Field(min_length=12, max_length=12, description="SHA-256[:12] do student_id original")]
    class_id: Annotated[str, Field(min_length=1, max_length=50)]
    subject: SubjectEnum
    teacher_name: Annotated[str, Field(default="Não Informado", max_length=100)]
    assessment_name: Annotated[str, Field(default="Nota Geral", max_length=100)]
    grade: Annotated[float, Field(ge=0.0, le=100.0)]
    period: Annotated[str, Field(pattern=r"^\d{4}-(T[1-4]|S[12])$", description="Ex: 2024-T1, 2024-S2")]
    recorded_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("grade", mode="before")
    @classmethod
    def normalize_grade(cls, v: object) -> float:
        """Aceita vírgula como separador decimal (ex: '7,5' → 7.5)."""
        if isinstance(v, str):
            v = v.replace(",", ".")
        return round(float(v), 1)

    @property
    def performance_level(self) -> PerformanceLevel:
        if self.grade >= 85.0:
            return PerformanceLevel.EXCELLENCE
        if self.grade >= 60.0:
            return PerformanceLevel.PASSING
        if self.grade >= 50.0:
            return PerformanceLevel.AT_RISK
        return PerformanceLevel.FAILING

    @staticmethod
    def hash_student_id(student_id: str) -> str:
        """Pseudonimização LGPD: SHA-256[:12] do identificador do aluno."""
        return hashlib.sha256(student_id.encode("utf-8")).hexdigest()[:12]


class StudentProfile(BaseModel):
    """Perfil agregado de desempenho de um aluno (sem PII)."""

    model_config = ConfigDict(strict=True, frozen=False)

    student_hash: Annotated[str, Field(min_length=12, max_length=12)]
    class_id: str
    grades: list[GradeRecord] = Field(default_factory=list)
    attendance_percent: Annotated[float, Field(ge=0.0, le=100.0)] = 100.0

    @property
    def average_grade(self) -> float:
        if not self.grades:
            return 0.0
        return round(sum(g.grade for g in self.grades) / len(self.grades), 1)

    @property
    def weak_subjects(self) -> list[SubjectEnum]:
        return [g.subject for g in self.grades if g.grade < 6.0]

class TeacherProfile(BaseModel):
    """Perfil agregado de desempenho das turmas de um professor."""
    model_config = ConfigDict(strict=True, frozen=False)
    
    teacher_name: str
    subjects: set[SubjectEnum] = Field(default_factory=set)
    classes_taught: set[str] = Field(default_factory=set)
    records: list[GradeRecord] = Field(default_factory=list)

    @property
    def average_grade(self) -> float:
        if not self.records:
            return 0.0
        return round(sum(g.grade for g in self.records) / len(self.records), 1)
        
    @property
    def at_risk_percent(self) -> float:
        if not self.records:
            return 0.0
        at_risk = sum(1 for g in self.records if g.grade < 6.0)
        return round((at_risk / len(self.records)) * 100, 1)

class ClassProfile(BaseModel):
    """Perfil agregado de desempenho de uma turma."""
    model_config = ConfigDict(strict=True, frozen=False)
    
    class_id: str
    records: list[GradeRecord] = Field(default_factory=list)

    @property
    def average_grade(self) -> float:
        if not self.records:
            return 0.0
        return round(sum(g.grade for g in self.records) / len(self.records), 1)

    @property
    def weak_subjects(self) -> list[str]:
        subject_averages = {}
        for r in self.records:
            subject_averages.setdefault(r.subject.value, []).append(r.grade)
        
        weak = []
        for subj, grades in subject_averages.items():
            if sum(grades) / len(grades) < 6.0:
                weak.append(subj)
        return weak


class GroupingResult(BaseModel):
    """Resultado de agrupamento cross-turma de alunos."""

    model_config = ConfigDict(strict=True, frozen=False)

    group_id: str
    student_hashes: Annotated[list[str], Field(min_length=3)]
    shared_weaknesses: list[SubjectEnum]
    similarity_score: Annotated[float, Field(ge=0.0, le=1.0)]
    recommended_intervention: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("student_hashes")
    @classmethod
    def validate_group_size(cls, v: list[str]) -> list[str]:
        if len(v) > 15:
            raise ValueError(f"Grupo excede limite máximo de 15 alunos: {len(v)}")
        return v


class AIRecommendation(BaseModel):
    """Recomendação pedagógica gerada pela IA via Ollama.

    O campo `model_used` usa SupportedModel para garantir que apenas modelos
    aprovados sejam registrados no audit trail. Para adicionar um novo modelo,
    inclua-o em SupportedModel e em pedagogical_rules.json["models"].
    """

    model_config = ConfigDict(strict=True, frozen=False)

    group_id: str
    recommendations: Annotated[list[str], Field(min_length=1, max_length=5)]
    subjects_addressed: list[SubjectEnum]
    disclaimer: str = "IA auxilia, humano decide. Valide com seu julgamento pedagógico antes de agir."
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    model_used: SupportedModel = SupportedModel.MISTRAL

    @model_validator(mode="after")
    def validate_disclaimer_present(self) -> AIRecommendation:
        if not self.disclaimer:
            raise ValueError("Disclaimer pedagógico é obrigatório em toda recomendação de IA.")
        return self


class AuditLogEntry(BaseModel):
    """Registro de auditoria imutável para conformidade LGPD."""

    model_config = ConfigDict(strict=True, frozen=True)  # frozen=True → imutável

    event_id: str
    event_type: Annotated[str, Field(description="Ex: upload, group_created, ai_recommendation, human_approved")]
    actor: str  # usuario/sistema que gerou o evento
    tenant_id: str = "school_mvp"  # single-school no MVP; multi-tenant futuro
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: dict = Field(default_factory=dict)
    # PII NUNCA nos details — use hashes
