"""
src/ui/app.py
=============
Aplicação Streamlit principal — EduAnalytics MVP.
Agente 4 — UI & UX.

Fluxo: Upload → Preview → Agrupamento → IA (opcional) → Aprovação → Auditoria → Export
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import streamlit as st

# ---------------------------------------------------------------------------
# Configuração da página (deve ser o primeiro comando Streamlit)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="EduAnalytics MVP",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "EduAnalytics MVP — Análise de desempenho escolar com IA local."},
)

from src.ui.components.uploader import render_uploader
from src.ui.components.grade_table import render_grade_table
from src.ui.components.group_view import render_group_view
from src.ui.components.ai_panel import render_ai_panel
from src.ui.components.audit_view import render_audit_view
from src.ui.components.teacher_view import render_teacher_view
from src.ui.components.curriculum_view import render_curriculum_view


# ---------------------------------------------------------------------------
# Estado da sessão
# ---------------------------------------------------------------------------

def init_state() -> None:
    """Inicializa st.session_state com valores padrão. Nunca usa variáveis globais."""
    defaults: dict[str, Any] = {
        "records": [],            # list[GradeRecord]
        "groups": [],             # list[GroupingResult]
        "ai_recommendations": [], # list[AIRecommendation]
        "audit_log": [],          # list[AuditLogEntry dict]
        "upload_filename": None,
        "ai_loading": False,
        "active_tab": "upload",
        "period": "2024-T1",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _log_audit(event_type: str, actor: str, details: dict) -> None:
    """Registra evento imutável no audit log da sessão."""
    entry = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "actor": actor,
        "tenant_id": "school_mvp",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "details": details,
    }
    st.session_state.audit_log.append(entry)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar() -> None:
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/combo-chart--v1.png", width=64)
        st.title("EduAnalytics")
        st.caption("MVP v0.1.0 · Local · LGPD-compliant")
        st.divider()

        st.subheader("⚙️ Configurações")
        period = st.text_input(
            "Período letivo",
            value=st.session_state.period,
            placeholder="ex: 2024-T1",
            help="Formato: AAAA-T1/T2/T3/T4 ou AAAA-S1/S2",
        )
        if period != st.session_state.period:
            st.session_state.period = period

        st.divider()
        st.subheader("📊 Status")
        n_records = len(st.session_state.records)
        n_groups = len(st.session_state.groups)
        n_recs = len(st.session_state.ai_recommendations)
        st.metric("Notas carregadas", n_records)
        st.metric("Grupos identificados", n_groups)
        st.metric("Recomendações IA", n_recs)

        st.divider()
        st.caption("🔒 IA auxilia, humano decide.")
        st.caption("Dados pseudonimizados — LGPD by Design.")

        if st.button("🗑️ Limpar sessão", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


# ---------------------------------------------------------------------------
# Tabs principais
# ---------------------------------------------------------------------------

def render_main() -> None:
    st.title("🎯 EduAnalytics MVP")
    st.caption("Análise de desempenho escolar com IA local · Dados pseudonimizados")

    tab_upload, tab_groups, tab_curriculum, tab_teachers, tab_ai, tab_audit = st.tabs([
        "📤 Upload & Preview",
        "👥 Agrupamentos",
        "📚 Currículo",
        "👨‍🏫 Professores",
        "🤖 Recomendações IA",
        "📋 Auditoria",
    ])

    with tab_upload:
        _tab_upload()

    with tab_groups:
        _tab_groups()

    with tab_curriculum:
        if st.session_state.records:
            render_curriculum_view(st.session_state.records)
        else:
            st.info("💡 Faça o upload de um boletim na aba Upload.")

    with tab_teachers:
        if st.session_state.records:
            render_teacher_view(st.session_state.records)
        else:
            st.info("💡 Faça o upload de um boletim na aba Upload.")

    with tab_ai:
        _tab_ai()

    with tab_audit:
        _tab_audit()


# ── Tab: Upload ──────────────────────────────────────────────────────────

def _tab_upload() -> None:
    records = render_uploader(period=st.session_state.period)

    if records:
        st.session_state.records = records
        st.session_state.groups = []
        st.session_state.ai_recommendations = []
        _log_audit(
            "upload",
            actor="professor",
            details={"total_records": len(records), "period": st.session_state.period},
        )
        st.success(f"✅ {len(records)} notas carregadas com sucesso!")

        st.divider()
        render_grade_table(st.session_state.records)

        # Gera os agrupamentos automaticamente caso ainda não existam
        if not st.session_state.groups:
            with st.spinner("Analisando dados e agrupando alunos..."):
                from src.analytics.grouping import group_students_by_weakness
                try:
                    groups = group_students_by_weakness(st.session_state.records)
                    st.session_state.groups = groups
                    _log_audit(
                        "grouping_created",
                        actor="sistema",
                        details={"groups_formed": len(groups)},
                    )
                except Exception as e:
                    st.error(f"Erro ao agrupar: {e}")
                    
        if st.session_state.groups:
            st.success(f"✅ {len(st.session_state.groups)} grupos identificados automaticamente! Explore as outras abas para ver os resultados.")
        else:
            st.info("Todos os alunos parecem estar com notas acima da média. Nenhum grupo de risco formado!")


# ── Tab: Grupos ──────────────────────────────────────────────────────────

def _tab_groups() -> None:
    if not st.session_state.groups:
        st.info("💡 Faça o upload de um boletim e clique em 'Agrupar alunos' na aba Upload.")
        return
    render_group_view(st.session_state.groups)


# ── Tab: IA ───────────────────────────────────────────────────────────────

def _tab_ai() -> None:
    if not st.session_state.groups:
        st.info("💡 Crie agrupamentos primeiro (aba Upload).")
        return

    st.info(
        "🤖 **IA auxilia, humano decide.**  \n"
        "As recomendações abaixo são geradas pela IA local (Ollama) e requerem sua aprovação "
        "antes de qualquer ação. Valide com seu julgamento pedagógico.",
        icon="⚠️",
    )

    approved = render_ai_panel(
        groups=st.session_state.groups,
        existing_recommendations=st.session_state.ai_recommendations,
        on_approve=lambda rec, approver: _handle_ai_approval(rec, approver),
    )

    if approved:
        st.session_state.ai_recommendations.extend(approved)


def _handle_ai_approval(recommendation: dict, approver: str) -> None:
    _log_audit(
        "ai_recommendation_approved",
        actor=approver,
        details={
            "group_id": recommendation.get("group_id"),
            "model_used": recommendation.get("model_used"),
        },
    )


# ── Tab: Auditoria ────────────────────────────────────────────────────────

def _tab_audit() -> None:
    render_audit_view(st.session_state.audit_log)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    init_state()
    render_sidebar()
    render_main()


if __name__ == "__main__":
    main()
