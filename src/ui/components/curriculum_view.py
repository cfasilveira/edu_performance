import pandas as pd
import streamlit as st
from contracts.data_models import GradeRecord
from src.models.grade import compute_curriculum_statistics

def render_curriculum_view(records: list[GradeRecord]) -> None:
    st.subheader("📚 Desempenho por Tópico (Currículo)")
    stats = compute_curriculum_statistics(records)
    
    if not stats:
        st.info("Nenhuma estatística de currículo disponível.")
        return

    df = pd.DataFrame([
        {
            "Tópico/Avaliação": topic,
            "Média Geral": s["mean"],
            "Alunos em Risco (%)": s["at_risk_pct"],
            "Total de Notas": int(s["count"]),
        }
        for topic, s in stats.items()
    ])
    
    def _color_curriculum(row):
        if row["Alunos em Risco (%)"] > 40:
            return ["background-color: #ffcccc; color: #900000; font-weight: bold;"] * len(row)
        return [""] * len(row)
        
    styled = df.style.apply(_color_curriculum, axis=1).format({"Média Geral": "{:.1f}", "Alunos em Risco (%)": "{:.1f}%"})
    st.dataframe(styled, use_container_width=True)
    
    st.caption("🚨 Linhas em vermelho (Risco > 40%) indicam a necessidade de **reforço de carga horária** ou **mais tarefas** para fixação do tópico.")
