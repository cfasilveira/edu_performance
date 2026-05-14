"""
src/ui/components/grade_table.py
=================================
Componente de visualização de notas (sem PII).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from contracts.data_models import GradeRecord
from src.models.grade import PASSING_THRESHOLD, compute_class_statistics

__all__ = ["render_grade_table"]


def render_grade_table(records: list[GradeRecord]) -> None:
    """Renderiza tabela de notas e estatísticas por disciplina.

    Exibe apenas student_hash[:6] como referência — nunca nome completo.

    Args:
        records: Lista de GradeRecord pseudonimizados.
    """
    st.subheader("📊 Visão Geral das Notas")

    # ── Estatísticas por disciplina ───────────────────────────────────────
    stats = compute_class_statistics(records)
    if stats:
        cols = st.columns(min(len(stats), 4))
        for i, (subject, s) in enumerate(stats.items()):
            col = cols[i % 4]
            delta_color = "inverse" if s["at_risk_pct"] > 30 else "normal"
            col.metric(
                label=subject,
                value=f"{s['mean']:.1f}",
                delta=f"{s['at_risk_pct']:.0f}% em risco",
                delta_color=delta_color,
                help=f"Min: {s['min']} | Max: {s['max']} | Alunos: {int(s['count'])}",
            )

    st.divider()

    # ── Tabela de notas (sem PII) ─────────────────────────────────────────
    df = pd.DataFrame([
        {
            "ID (anonimizado)": r.student_hash[:6] + "…",
            "Turma": r.class_id,
            "Disciplina": r.subject.value,
            "Nota": r.grade,
            "Status": _status_label(r.grade),
            "Período": r.period,
        }
        for r in records
    ])

    # Coloração condicional
    def _color_row(row):
        if row["Nota"] < PASSING_THRESHOLD:
            return ["background-color: #fff0f0"] * len(row)
        if row["Nota"] >= 85:
            return ["background-color: #f0fff0"] * len(row)
        return [""] * len(row)

    styled = df.style.apply(_color_row, axis=1).format({"Nota": "{:.1f}"})

    st.dataframe(styled, use_container_width=True, height=400)
    st.caption(
        f"📌 {len(records)} notas carregadas · "
        f"IDs exibidos com 6 caracteres (anonimizados) · "
        f"Vermelho = abaixo de {PASSING_THRESHOLD:.0f} · Verde = excelência (≥ 85)"
    )


def _status_label(grade: float) -> str:
    if grade >= 85:
        return "✅ Excelente"
    if grade >= 60:
        return "🟡 Aprovado"
    if grade >= 50:
        return "🟠 Em risco"
    return "🔴 Reprovado"
