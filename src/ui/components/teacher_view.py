import altair as alt
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
            "Cor": "#ff4b4b" if s["at_risk_pct"] > 50 else "#3dd56d" if s["mean"] >= 8.5 else "#3366cc"
        }
        for teacher, s in stats.items()
    ])
    
    # Cria o gráfico de barras
    base = alt.Chart(df).encode(
        x=alt.X('Média Geral das Turmas:Q', scale=alt.Scale(domain=[0, 10]), title="Média Geral"),
        y=alt.Y('Professor:N', sort='-x', title="Professor")
    )
    
    bars = base.mark_bar().encode(
        color=alt.Color('Cor:N', scale=None)  # Usa a cor exata da coluna 'Cor'
    )
    
    text = base.mark_text(
        align='left',
        baseline='middle',
        dx=3  # Espaçamento para a direita do fim da barra
    ).encode(
        text=alt.Text('Média Geral das Turmas:Q', format='.1f')
    )
    
    chart = (bars + text).properties(height=max(300, len(df) * 40))
    st.altair_chart(chart, use_container_width=True)
    
    # Exibe a tabela original abaixo para consulta dos percentuais
    st.markdown("### Detalhamento")
    
    def _color_teacher(row):
        if row["Alunos em Risco (%)"] > 50:
            return ["background-color: #fff0f0"] * len(row)
        if row["Média Geral das Turmas"] >= 8.5:
            return ["background-color: #f0fff0"] * len(row)
        return [""] * len(row)
        
    styled = df.drop(columns=["Cor"]).style.apply(_color_teacher, axis=1).format({
        "Média Geral das Turmas": "{:.1f}", 
        "Alunos em Risco (%)": "{:.1f}%"
    })
    st.dataframe(styled, use_container_width=True)
    
    st.caption("🚨 Barras em vermelho indicam que mais de 50% dos alunos sob responsabilidade deste professor estão em risco. Verde indica excelência.")
    

