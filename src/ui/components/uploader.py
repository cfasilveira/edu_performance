"""
src/ui/components/uploader.py
==============================
Componente de upload seguro de boletins.
Agente 4 — UI & UX.
"""

from __future__ import annotations

import html

import streamlit as st

from contracts.data_models import GradeRecord
from src.io.gradebook_parser import GradebookParseError, parse_gradebook

__all__ = ["render_uploader"]

ALLOWED_TYPES = ["csv", "xlsx", "xls"]
MAX_SIZE_MB = 10


def render_uploader(period: str) -> list[GradeRecord]:
    """Renderiza o componente de upload e retorna records parseados.

    Args:
        period: Período letivo selecionado na sidebar.

    Returns:
        Lista de GradeRecord se upload bem-sucedido, lista vazia caso contrário.
    """
    st.subheader("📤 Upload de Boletim")
    st.caption(
        "Formatos aceitos: CSV, XLSX. Tamanho máximo: 10 MB.  \n"
        "⚠️ Seus dados são **pseudonimizados automaticamente** — nomes de alunos não são armazenados."
    )

    uploaded = st.file_uploader(
        "Selecione o boletim escolar",
        type=ALLOWED_TYPES,
        help="O arquivo deve conter colunas: aluno, turma, disciplina, nota, periodo (ou equivalentes).",
        label_visibility="collapsed",
    )

    if uploaded is None:
        st.info("👆 Faça o upload de um boletim para começar a análise.")
        return []

    # ── Validação de tamanho no cliente ──────────────────────────────────
    size_mb = uploaded.size / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        st.error(f"❌ Arquivo muito grande: {size_mb:.1f} MB (limite: {MAX_SIZE_MB} MB)")
        return []

    # ── Preview do nome (sanitizado) ──────────────────────────────────────
    safe_name = html.escape(uploaded.name)
    st.caption(f"📄 Arquivo: `{safe_name}` · {size_mb:.2f} MB")

    if not period or not period.strip():
        st.warning("⚠️ Defina o período letivo na barra lateral antes de continuar.")
        return []

    # ── Parse seguro ──────────────────────────────────────────────────────
    with st.spinner(f"Processando `{safe_name}`..."):
        try:
            ext = uploaded.name.rsplit(".", 1)[-1].lower()
            records = parse_gradebook(
                uploaded.read(),
                period=period,
                file_extension=ext,
            )
            return records

        except GradebookParseError as exc:
            st.error(f"❌ Erro no arquivo: {exc}")
            return []
        except Exception as exc:
            st.error(f"❌ Erro inesperado ao processar o arquivo. Tente novamente.")
            # Log do erro real (sem expor stack trace ao usuário)
            import structlog
            structlog.get_logger(__name__).error("upload_unexpected_error", error=str(exc))
            return []
