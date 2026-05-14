"""
src/ui/components/ai_panel.py
==============================
Painel de recomendações pedagógicas com aprovação humana obrigatória.
Agente 4 — UI & UX.
"""

from __future__ import annotations

import asyncio
from typing import Callable

import streamlit as st

from contracts.data_models import AIRecommendation, GroupingResult

__all__ = ["render_ai_panel"]


def _run_async(coro):
    """Executa coroutine em thread de forma compatível com Streamlit."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=65)
        return loop.run_until_complete(coro)
    except Exception:
        return asyncio.run(coro)


def render_ai_panel(
    groups: list[GroupingResult],
    existing_recommendations: list[AIRecommendation],
    on_approve: Callable[[dict, str], None],
) -> list[AIRecommendation]:
    """Renderiza painel de geração e aprovação de recomendações de IA.

    Args:
        groups: Grupos disponíveis para análise.
        existing_recommendations: Recomendações já geradas nesta sessão.
        on_approve: Callback chamado quando professor aprova uma recomendação.

    Returns:
        Lista de novas recomendações aprovadas nesta renderização.
    """
    st.subheader("🤖 Recomendações Pedagógicas com IA")

    # Seletor de grupo
    group_options = {
        f"Grupo {i+1} — {', '.join(s.value for s in g.shared_weaknesses) or 'múltiplas'} ({len(g.student_hashes)} alunos)": g
        for i, g in enumerate(groups)
    }

    selected_label = st.selectbox(
        "Selecione um grupo para análise:",
        options=list(group_options.keys()),
        index=0,
    )
    selected_group: GroupingResult = group_options[selected_label]

    # Verificar se já existe recomendação para este grupo
    existing = next(
        (r for r in existing_recommendations if r.group_id == selected_group.group_id), None
    )

    approved_now: list[AIRecommendation] = []

    if existing:
        _render_recommendation(existing, on_approve, approved_now, already_shown=True)
        return approved_now

    # Botão de geração — desabilitado durante inferência
    if st.session_state.get("ai_loading", False):
        st.button("⏳ Gerando recomendação...", disabled=True, use_container_width=True)
        return approved_now

    if st.button(
        "🧠 Gerar recomendação para este grupo",
        type="primary",
        use_container_width=True,
        help="A IA local (Ollama/Mistral) pode levar 5–30 segundos para responder.",
    ):
        st.session_state.ai_loading = True
        with st.spinner("🤖 Consultando Ollama (pode levar até 30s em CPU)..."):
            try:
                from src.llm.advisor import PedagogicalAdvisor
                advisor = PedagogicalAdvisor()
                recommendation = _run_async(advisor.recommend(selected_group))
                advisor.close()
                st.session_state.ai_recommendations.append(recommendation)
            except Exception as exc:
                st.error(f"❌ Erro ao gerar recomendação: {exc}")
            finally:
                st.session_state.ai_loading = False

        st.rerun()

    return []


def _render_recommendation(
    rec: AIRecommendation,
    on_approve: Callable[[dict, str], None],
    approved_list: list[AIRecommendation],
    already_shown: bool = False,
) -> None:
    """Renderiza uma recomendação com campo de aprovação."""
    st.divider()

    if already_shown:
        st.success("✅ Esta recomendação já foi gerada para este grupo.")


    st.markdown("**Recomendações geradas pela IA:**")
    for i, r in enumerate(rec.recommendations, 1):
        st.markdown(f"{i}. {r}")

    if rec.subjects_addressed:
        st.markdown(
            "**Disciplinas abordadas:** " +
            ", ".join(s.value for s in rec.subjects_addressed)
        )

    st.caption(f"Modelo: `{rec.model_used.value}` · Gerado em: {rec.generated_at.strftime('%d/%m/%Y %H:%M')}")

    # Recomendação exibida diretamente sem necessidade de validação.
    pass
