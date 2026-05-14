"""
src/ui/components/group_view.py
================================
Componente de visualização de grupos cross-turma.
"""

from __future__ import annotations

import streamlit as st

from contracts.data_models import GroupingResult

__all__ = ["render_group_view"]


def render_group_view(groups: list[GroupingResult]) -> None:
    """Renderiza grupos de alunos agrupados por dificuldades compartilhadas.

    Exibe apenas hashes truncados — nunca dados de identificação.

    Args:
        groups: Lista de GroupingResult ordenada por similarity_score.
    """
    st.subheader("👥 Grupos Identificados")
    st.caption(
        f"**{len(groups)} grupos** formados cross-turma · "
        "Alunos com dificuldades compartilhadas, independente de turma · "
        "IDs são anonimizados."
    )

    if not groups:
        st.info("Nenhum grupo identificado. Todos os alunos podem estar aprovados.")
        return

    for i, group in enumerate(groups, start=1):
        weaknesses = ", ".join(s.value for s in group.shared_weaknesses) or "—"
        size = len(group.student_hashes)
        sim_pct = f"{group.similarity_score:.0%}"

        with st.expander(
            f"Grupo {i} · {size} alunos · Dificuldades: **{weaknesses}** · Similaridade: {sim_pct}",
            expanded=(i == 1),
        ):
            col_a, col_b = st.columns([2, 1])

            with col_a:
                st.markdown("**Alunos no grupo** (IDs anonimizados):")
                hashes_display = [f"`{h[:6]}…`" for h in group.student_hashes]
                st.markdown(", ".join(hashes_display))

            with col_b:
                st.metric("Similaridade", sim_pct)
                st.metric("Tamanho do grupo", size)

            if group.shared_weaknesses:
                st.markdown("**Disciplinas com dificuldade compartilhada:**")
                for subj in group.shared_weaknesses:
                    st.markdown(f"- 🔴 {subj.value}")

            if group.recommended_intervention:
                st.info(f"💡 {group.recommended_intervention}")

    st.divider()
    st.caption("💡 Para gerar recomendações pedagógicas, vá para a aba **Recomendações IA**.")
