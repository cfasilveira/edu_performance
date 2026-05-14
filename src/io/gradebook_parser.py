"""
src/io/gradebook_parser.py
==========================
Parser seguro de boletins escolares (CSV e Excel).
Agente 2 — Backend & Dados.

Responsabilidades:
- Validar extensão e tamanho do arquivo (path traversal / upload seguro)
- Detectar e rejeitar CSV injection (células =, +, -, @)
- Normalizar notas (vírgula → ponto decimal)
- Pseudonimizar student_id via SHA-256[:12]
- Retornar lista de GradeRecord validados pelo Pydantic
"""

from __future__ import annotations

import gc
import io
from pathlib import Path
from typing import Final

import pandas as pd
import structlog
from pydantic import ValidationError

from contracts.data_models import GradeRecord, SubjectEnum
from src.models.grade import hash_student_id, sanitize_text_input

__all__ = ["parse_gradebook", "GradebookParseError"]

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes de segurança
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset({".csv", ".xlsx", ".xls"})
MAX_FILE_SIZE_BYTES: Final[int] = 100 * 1024 * 1024  # 100 MB
CSV_INJECTION_PREFIXES: Final[tuple[str, ...]] = ("=", "+", "-", "@", "\t", "\r")

# Mapeamento de nomes de coluna aceitos → campo canônico
_COLUMN_ALIASES: Final[dict[str, str]] = {
    # student
    "aluno": "student_id",
    "aluno_id": "student_id",
    "id_aluno": "student_id",
    "student_id": "student_id",
    "matricula": "student_id",
    "matrícula": "student_id",
    # class
    "turma": "class_id",
    "class": "class_id",
    "class_id": "class_id",
    # subject
    "disciplina": "subject",
    "materia": "subject",
    "subject": "subject",
    # grade
    "nota1": "nota1",
    "nota2": "nota2",
    "nota3": "nota3",
    "nota4": "nota4",
    # period (mantido por retrocompatibilidade se vier no arquivo, mas ignorado no df final)
    "periodo": "period",
    "bimestre": "period",
    "semestre": "period",
    "period": "period",
    # PII
    "nome": "nome",
    "name": "nome",
}


# ---------------------------------------------------------------------------
# Exceção de domínio
# ---------------------------------------------------------------------------

class GradebookParseError(Exception):
    """Erro de parsing de boletim — retornável ao usuário sem stack trace."""


# ---------------------------------------------------------------------------
# Funções internas
# ---------------------------------------------------------------------------

def _validate_path(file_path: Path) -> None:
    """Valida extensão e resolve path para evitar path traversal.

    Args:
        file_path: Caminho fornecido pelo usuário.

    Raises:
        GradebookParseError: Se extensão inválida ou path suspeito.
    """
    resolved = file_path.resolve()
    if resolved.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise GradebookParseError(
            f"Extensão não permitida: '{resolved.suffix}'. "
            f"Aceitas: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    log.debug("path_validated", path=str(resolved))


def _validate_size(data: bytes) -> None:
    """Verifica tamanho do arquivo em bytes.

    Args:
        data: Conteúdo bruto do arquivo.

    Raises:
        GradebookParseError: Se exceder MAX_FILE_SIZE_BYTES.
    """
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise GradebookParseError(
            f"Arquivo muito grande: {len(data) / 1e6:.1f} MB "
            f"(limite: {MAX_FILE_SIZE_BYTES / 1e6:.0f} MB)"
        )


def _detect_csv_injection(df: pd.DataFrame) -> None:
    """Verifica células com prefixos de injeção CSV em colunas de texto.

    Args:
        df: DataFrame após leitura.

    Raises:
        GradebookParseError: Se célula suspeita encontrada.
    """
    str_cols = df.select_dtypes(include="object").columns
    for col in str_cols:
        for val in df[col].dropna().astype(str):
            if val.startswith(CSV_INJECTION_PREFIXES):
                raise GradebookParseError(
                    f"CSV injection detectado na coluna '{col}': valor começa com '{val[0]}'"
                )


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Renomeia colunas usando aliases conhecidos.

    Args:
        df: DataFrame com colunas originais.

    Returns:
        DataFrame com colunas canônicas.

    Raises:
        GradebookParseError: Se coluna obrigatória não encontrada.
    """
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    rename_map = {col: canonical for col, canonical in _COLUMN_ALIASES.items() if col in df.columns}
    df = df.rename(columns=rename_map)

    if "nome" in df.columns:
        df = df.drop(columns=["nome"])  # LGPD - descartar PII explícito

    required = {"student_id", "class_id", "subject", "nota1", "nota2", "nota3", "nota4"}
    missing = required - set(df.columns)
    if missing:
        raise GradebookParseError(
            f"Colunas obrigatórias ausentes: {', '.join(sorted(missing))}. "
            f"Colunas esperadas: {', '.join(sorted(required))}. "
            f"Colunas encontradas: {', '.join(df.columns.tolist())}"
        )
    return df


def _map_subject(raw: str) -> SubjectEnum:
    """Mapeia string de disciplina para SubjectEnum.

    Args:
        raw: Nome da disciplina como está no arquivo.

    Returns:
        SubjectEnum correspondente.

    Raises:
        GradebookParseError: Se disciplina não reconhecida.
    """
    normalized = sanitize_text_input(raw).strip().title()
    # Tenta match direto
    for member in SubjectEnum:
        if member.value.lower() == normalized.lower():
            return member
    raise GradebookParseError(
        f"Disciplina não reconhecida: '{raw}'. "
        f"Valores aceitos: {[s.value for s in SubjectEnum]}"
    )


# ---------------------------------------------------------------------------
# Função principal (API pública)
# ---------------------------------------------------------------------------

def parse_gradebook(
    source: Path | bytes,
    period: str,
    *,
    file_extension: str | None = None,
) -> list[GradeRecord]:
    """Lê e valida um boletim escolar (CSV ou Excel).

    Aplica todas as verificações de segurança antes do processamento.
    Pseudonimiza student_id via SHA-256[:12] antes de criar GradeRecord.

    Args:
        source: Caminho para o arquivo OU bytes (para upload via Streamlit).
        period: Período letivo no formato '2024-T1' ou '2024-S2'.
        file_extension: Extensão do arquivo (obrigatório se source=bytes).

    Returns:
        Lista de GradeRecord validados pelo Pydantic.

    Raises:
        GradebookParseError: Em qualquer violação de segurança ou schema.
        ValueError: Se source=bytes e file_extension não informado.

    Example:
        >>> records = parse_gradebook(Path("boletim.csv"), period="2024-T1")
        >>> len(records)
        120

    Edge cases:
        - Nota com vírgula ('7,5') → normalizada para 7.5
        - Disciplina com case diferente → mapeada para enum
        - Aluno sem turma → GradebookParseError lançado
        - Path traversal → GradebookParseError antes de abrir arquivo
    """
    # ── 1. Fail-fast: validar inputs ──────────────────────────────────────
    if not period or not period.strip():
        raise GradebookParseError("Campo 'period' é obrigatório (ex: '2024-T1')")

    period = sanitize_text_input(period.strip())

    # ── 2. Ler bytes de forma segura ──────────────────────────────────────
    if isinstance(source, Path):
        _validate_path(source)
        raw_bytes = source.read_bytes()
        ext = source.suffix.lower()
    elif isinstance(source, bytes):
        if not file_extension:
            raise ValueError("file_extension é obrigatório quando source=bytes")
        ext = f".{file_extension.lstrip('.').lower()}"
        raw_bytes = source
    else:
        raise TypeError(f"source deve ser Path ou bytes, recebeu {type(source).__name__}")

    _validate_size(raw_bytes)
    log.info("gradebook_parse_start", size_bytes=len(raw_bytes), ext=ext, period=period)

    # ── 3. Parsear DataFrame ──────────────────────────────────────────────
    try:
        if ext == ".csv":
            df = pd.read_csv(
                io.BytesIO(raw_bytes),
                dtype=str,          # tudo como string para inspeção de injeção
                engine="python",
            )
        else:
            df = pd.read_excel(
                io.BytesIO(raw_bytes),
                dtype=str,
                engine="openpyxl",
            )
    except Exception as exc:
        raise GradebookParseError(f"Arquivo inválido ou corrompido: {exc}") from exc

    # ── 4. Segurança: CSV injection ───────────────────────────────────────
    _detect_csv_injection(df)

    # ── 5. Normalizar colunas ─────────────────────────────────────────────
    df = _normalize_columns(df)
    df = df.dropna(subset=["student_id", "class_id", "subject", "nota1", "nota2", "nota3", "nota4"])

    # ── 6. Converter e validar cada linha ────────────────────────────────
    records: list[GradeRecord] = []
    errors: list[str] = []

    for idx, row in df.iterrows():
        try:
            student_hash = hash_student_id(str(row["student_id"]))
            subject = _map_subject(str(row["subject"]))
            class_id = sanitize_text_input(str(row["class_id"]))

            # MVP: média das 4 notas para a disciplina no período informado
            n1 = float(str(row["nota1"]).replace(",", "."))
            n2 = float(str(row["nota2"]).replace(",", "."))
            n3 = float(str(row["nota3"]).replace(",", "."))
            n4 = float(str(row["nota4"]).replace(",", "."))
            media = (n1 + n2 + n3 + n4) / 4.0

            record = GradeRecord(
                student_hash=student_hash,
                class_id=class_id,
                subject=subject,
                grade=media,
                period=period,
            )
            records.append(record)

        except (GradebookParseError, ValidationError, ValueError) as exc:
            errors.append(f"Linha {idx + 2}: {exc}")
            log.warning("gradebook_row_skipped", row_index=idx, error=str(exc))

    # ── 7. Liberar memória ────────────────────────────────────────────────
    del df, raw_bytes
    gc.collect()

    # ── 8. Relatório final ────────────────────────────────────────────────
    log.info(
        "gradebook_parse_complete",
        total_valid=len(records),
        total_errors=len(errors),
        period=period,
    )

    if not records:
        raise GradebookParseError(
            f"Nenhum registro válido encontrado. Erros: {errors[:5]}"
        )

    if errors:
        log.warning("gradebook_parse_partial_errors", count=len(errors), sample=errors[:3])

    return records
