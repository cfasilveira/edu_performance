"""
src/ui/components/audit_view.py
================================
Componente de visualização do log de auditoria.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

__all__ = ["render_audit_view"]

_EVENT_ICONS = {
    "upload": "📤",
    "grouping_created": "👥",
    "ai_recommendation_approved": "✅",
    "export": "📥",
}


def render_audit_view(audit_log: list[dict]) -> None:
    """Renderiza o log imutável de auditoria da sessão.

    Args:
        audit_log: Lista de dicts com eventos da sessão atual.
    """
    st.subheader("📋 Log de Auditoria")
    st.caption(
        "Registro imutável de todas as ações desta sessão. "
        "Conformidade LGPD — sem PII registrada."
    )

    if not audit_log:
        st.info("Nenhuma ação registrada ainda. Faça o upload de um boletim para começar.")
        return

    # ── Tabela resumo ─────────────────────────────────────────────────────
    df = pd.DataFrame([
        {
            "Tipo": f"{_EVENT_ICONS.get(e['event_type'], '📌')} {e['event_type']}",
            "Ator": e.get("actor", "—"),
            "Timestamp": e.get("timestamp", "—")[:19].replace("T", " "),
            "Tenant": e.get("tenant_id", "—"),
        }
        for e in audit_log
    ])
    st.dataframe(df, use_container_width=True)

    # ── Detalhe de cada evento ────────────────────────────────────────────
    st.divider()
    st.markdown("**Detalhes dos eventos:**")
    for entry in reversed(audit_log):
        icon = _EVENT_ICONS.get(entry["event_type"], "📌")
        with st.expander(
            f"{icon} `{entry['event_type']}` · {entry.get('timestamp', '')[:19].replace('T', ' ')} · {entry.get('actor', '—')}",
            expanded=False,
        ):
            st.json(entry.get("details", {}))
            st.caption(f"Event ID: `{entry.get('event_id', '—')}`")

    # ── Export ────────────────────────────────────────────────────────────
    st.divider()
    if st.download_button(
        label="📥 Exportar log de auditoria (JSON)",
        data=json.dumps(audit_log, indent=2, ensure_ascii=False, default=str),
        file_name="audit_log.json",
        mime="application/json",
        use_container_width=True,
    ):
        pass  # download_button gerencia o próprio evento
