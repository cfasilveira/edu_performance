import pandas as pd
import streamlit as st
from contracts.data_models import GradeRecord
from src.models.grade import compute_teacher_statistics

def render_teacher_view(records: list[GradeRecord]) -> None:
    st.subheader("👨‍🏫 Desempenho do Corpo Docente")
    stats = compute_teacher_statistics(records)
    
    if not stats:
        st.info("Nenhuma estatística de professor disponível.")
        return

    df = pd.DataFrame([
        {
            "Professor": teacher,
            "Média Geral das Turmas": s["mean"],
            "Alunos em Risco (%)": s["at_risk_pct"],
            "Total de Notas": int(s["count"]),
        }
        for teacher, s in stats.items()
    ])
    
    def _color_teacher(row):
        if row["Alunos em Risco (%)"] > 50:
            return ["background-color: #fff0f0"] * len(row)
        if row["Média Geral das Turmas"] >= 8.5:
            return ["background-color: #f0fff0"] * len(row)
        return [""] * len(row)
        
    styled = df.style.apply(_color_teacher, axis=1).format({"Média Geral das Turmas": "{:.1f}", "Alunos em Risco (%)": "{:.1f}%"})
    st.dataframe(styled, use_container_width=True)
    
    st.caption("🚨 Linhas em vermelho indicam que mais de 50% dos alunos sob responsabilidade deste professor estão em risco. Verde indica excelência.")
