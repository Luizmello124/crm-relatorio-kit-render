import streamlit as st
import pandas as pd
import altair as alt
from io import BytesIO
import xlsxwriter

# ============================
# CONFIGURAÇÃO BÁSICA
# ============================
st.set_page_config(page_title="Relatório KIT CRM", layout="wide")

st.title("📊 Relatório KIT - CRM")
st.markdown("Gere relatórios filtrados e gráficos de forma simples.")

# ============================
# UPLOAD DO ARQUIVO
# ============================
uploaded_file = st.file_uploader("Selecione o arquivo CSV exportado do CRM", type=["csv"])

if uploaded_file:
    # Lê o arquivo
    df = pd.read_csv(uploaded_file)

    # Mostra preview
    st.subheader("Pré-visualização dos dados")
    st.dataframe(df.head())

    # ============================
    # FILTROS
    # ============================
    with st.sidebar:
        st.header("Filtros")
        colunas_numericas = df.select_dtypes(include=['number']).columns.tolist()
        colunas_texto = df.select_dtypes(exclude=['number']).columns.tolist()

        filtros_texto = {}
        for col in colunas_texto:
            valores = df[col].dropna().unique().tolist()
            if len(valores) < 100:  # evita colunas gigantes
                filtro = st.multiselect(f"Filtrar por {col}", sorted(valores))
                if filtro:
                    filtros_texto[col] = filtro

        filtros_numericos = {}
        for col in colunas_numericas:
            min_val, max_val = float(df[col].min()), float(df[col].max())
            range_sel = st.slider(f"Intervalo de {col}", min_val, max_val, (min_val, max_val))
            filtros_numericos[col] = range_sel

    # Aplica filtros
    df_filtrado = df.copy()
    for col, valores in filtros_texto.items():
        df_filtrado = df_filtrado[df_filtrado[col].isin(valores)]
    for col, (min_val, max_val) in filtros_numericos.items():
        df_filtrado = df_filtrado[(df_filtrado[col] >= min_val) & (df_filtrado[col] <= max_val)]

    st.subheader("📄 Dados Filtrados")
    st.dataframe(df_filtrado)

    # ============================
    # GRÁFICOS
    # ============================
    st.subheader("📈 Gráficos")
    colunas_grafico = df_filtrado.columns.tolist()

    eixo_x = st.selectbox("Eixo X", colunas_grafico)
    eixo_y = st.selectbox("Eixo Y", colunas_grafico)

    if eixo_x and eixo_y:
        chart = alt.Chart(df_filtrado).mark_bar().encode(
            x=eixo_x,
            y=eixo_y,
            tooltip=colunas_grafico
        ).interactive()
        st.altair_chart(chart, use_container_width=True)

    # ============================
    # EXPORTAR PARA EXCEL
    # ============================
    def to_excel(df):
        output = BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        df.to_excel(writer, index=False, sheet_name='Relatorio')
        writer.close()
        return output.getvalue()

    excel_data = to_excel(df_filtrado)

    st.download_button(
        label="📥 Baixar Excel filtrado",
        data=excel_data,
        file_name="relatorio_filtrado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("⬆️ Faça upload de um arquivo CSV para começar.")
