# app.py
# ----------------------------------------
# CRM Relatório Kit – Streamlit (versão com KPI "Em Proposta")
# ----------------------------------------

import io
from datetime import datetime

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st


# -----------------------------
# Configuração geral do app
# -----------------------------
st.set_page_config(page_title="Gerador de Relatório CRM", layout="wide")
alt.data_transformers.disable_max_rows()


# -----------------------------
# Helpers de normalização
# -----------------------------
FASE_ORDER = [
    "Em Atendimento",
    "Agendando Reunião",
    "Reuniões Agendadas",
    "Proposta e Negociação",
    "Negócio Fechado",
    "Abaixo de R$500K",
    "Fora do Perfil",
    "Sem Interesse",
    "Sem retorno",
    "Outros/Perdido",
]

FASE_COLOR = {
    # amarelo (morno)
    "Em Atendimento": "#f59e0b",
    # verdes (quente)
    "Agendando Reunião": "#22c55e",
    "Reuniões Agendadas": "#16a34a",
    "Proposta e Negociação": "#10b981",
    "Negócio Fechado": "#0ea5e9",
    # vermelhos/rosa (perdidos)
    "Abaixo de R$500K": "#ef4444",
    "Fora do Perfil": "#dc2626",
    "Sem Interesse": "#fb7185",
    "Sem retorno": "#fca5a5",
    "Outros/Perdido": "#991b1b",
}

# Conjunto robusto de rótulos possíveis para KPIs
REUNIOES_OPTS = {
    "Agendando Reunião",
    "Agendamento de reunião",
    "Agendamento Reunião",
    "Reuniões Agendadas",
    "Reunião agendada",
}
PROPOSTA_OPTS = {
    "Proposta e Negociação",
    "Proposta e negociação",
    "Proposta e Negociação -",
}
VENDAS_OPTS = {
    "Negócio Fechado",
    "Negócios Fechado",
    "Negócios Fechados",
    "Negocio Fechado",
    "Negócio fechado",
}


def normalize_fase(s: pd.Series) -> pd.Series:
    """Normaliza variações comuns de rótulos de fase."""
    s = s.fillna("").astype(str).str.strip()

    # mapas simples
    map_direct = {
        "Em atendimento": "Em Atendimento",
        "Em Atendimento": "Em Atendimento",
        "Agendamento de reunião": "Agendando Reunião",
        "Agendamento Reunião": "Agendando Reunião",
        "Reunião agendada": "Reuniões Agendadas",
        "Reuniões Agendadas": "Reuniões Agendadas",
        "Proposta e negociação": "Proposta e Negociação",
        "Proposta e Negociação -": "Proposta e Negociação",
        "Negocio Fechado": "Negócio Fechado",
        "Negócios Fechado": "Negócio Fechado",
        "Negócios Fechados": "Negócio Fechado",
        "Abaixo de 500k": "Abaixo de R$500K",
        "Abaixo de R$500k": "Abaixo de R$500K",
        "Fora do perfil": "Fora do Perfil",
        "Sem Retorno": "Sem retorno",
        "Outros/Perdido": "Outros/Perdido",
        "Outros/Perdidos": "Outros/Perdido",
    }
    s = s.replace(map_direct)

    # se ainda tiver algo não mapeado, mantém original
    return s


def canal_from_fonte(fonte: str) -> str:
    """Mapeia a tag 'Fonte' para o Canal de Origem (inclui Base CLT/SEC)."""
    f = (fonte or "").strip().lower()

    if f in {"site"}:
        return "Google Ads"
    if f in {"lp"}:
        return "Impulsionamento Instagram"
    if "whatsapp" in f:
        return "Inbound"
    if f in {"indicação", "indicacao"}:
        return "Indicação"

    # Meta Ads (variações)
    if "meta ads" in f or "metaads" in f:
        if "face" in f or "facebook" in f:
            return "Trafego Pago - Face"
        if "insta" in f or "instagram" in f:
            return "Trafego Pago - Insta"

    # Prospecção ativa
    if "prospecção ativa" in f or "prospeccao ativa" in f:
        return "Prospecção Ativa"

    # Base CLT/SEC (pedido novo)
    if "base clt/sec" in f or "clt/sec" in f or "clt" in f and "sec" in f:
        return "Base CLT/SEC"

    return "Outros"


def full_dates(start, end):
    rng = pd.date_range(pd.to_datetime(start), pd.to_datetime(end), freq="D")
    return pd.DataFrame({"Dia": pd.to_datetime(rng)})


# -----------------------------
# Leitura e limpeza do CSV
# -----------------------------
st.title("Gerador de Relatório CRM")

uploaded_file = st.file_uploader("CSV do CRM", type=["csv"])
if not uploaded_file:
    st.info("Envie um CSV para começar.")
    st.stop()

# Pandas lendo com separador ';' (padrão do seu CRM); fallback para ','
try:
    base_df = pd.read_csv(uploaded_file, sep=";", encoding="utf-8", low_memory=False)
except Exception:
    uploaded_file.seek(0)
    base_df = pd.read_csv(uploaded_file, sep=",", encoding="utf-8", low_memory=False)

# Encontrar a *segunda* coluna "Motivo de perda"
motivos_cols = [c for c in base_df.columns if "motivo" in c.lower() and "perd" in c.lower()]
motivo_final = motivos_cols[-1] if motivos_cols else None

# Selecionar e renomear as colunas de interesse
col_map = {}
for c in base_df.columns:
    cl = c.strip().lower()
    if cl.startswith("fase") or "fase" in cl:
        col_map[c] = "Fase"
    elif "respons" in cl:
        col_map[c] = "Responsável"
    elif "negócio" in cl or "negocio" in cl or "nome do negócio" in cl:
        col_map[c] = "Nome do Negócio"
    elif "fonte" in cl:
        col_map[c] = "Fonte"
    elif "criado" in cl or "criação" in cl or "data de criação" in cl:
        col_map[c] = "Criado"
    elif motivo_final and c == motivo_final:
        col_map[c] = "Motivo de perda"

use_cols = list(col_map.keys())
df = base_df[use_cols].rename(columns=col_map).copy()

# Datetime
if "Criado" in df.columns:
    df["Criado"] = pd.to_datetime(df["Criado"], errors="coerce")

# Normalizações
df["_fase_norm"] = normalize_fase(df.get("Fase", pd.Series(dtype=str)))
df["Canal de Origem"] = df.get("Fonte", pd.Series(dtype=str)).apply(canal_from_fonte)

# Filtros (UI)
with st.expander("Filtros", expanded=True):
    # período
    min_d = pd.to_datetime(df["Criado"]).min() if "Criado" in df.columns else None
    max_d = pd.to_datetime(df["Criado"]).max() if "Criado" in df.columns else None
    if not pd.isna(min_d) and not pd.isna(max_d):
        d_ini, d_fim = st.date_input(
            "Período (Criado)", value=(min_d.date(), max_d.date())
        )
    else:
        d_ini = datetime.today().date()
        d_fim = datetime.today().date()
        st.warning("Coluna 'Criado' ausente ou sem datas válidas — usando hoje.")

    total_vends = sorted(df["Responsável"].dropna().unique().tolist())
    vendedores_sel = st.multiselect(
        "Vendedoras", total_vends, default=total_vends, placeholder="Selecione…"
    )

    # atalhos
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
    with col_btn1:
        if st.button("Todos (Vendedoras)", use_container_width=True):
            vendedores_sel = total_vends
    with col_btn2:
        if st.button("Limpar (Vendedoras)", use_container_width=True):
            vendedores_sel = []

    total_canais = [
        "Google Ads",
        "Trafego Pago - Face",
        "Trafego Pago - Insta",
        "Impulsionamento Instagram",
        "Prospecção Ativa",
        "Inbound",
        "Indicação",
        "Outros",
        "Base CLT/SEC",
    ]
    canais_sel = st.multiselect(
        "Canais de Origem",
        total_canais,
        default=total_canais,
        placeholder="Selecione…",
    )

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Todos (Canais)", use_container_width=True):
            canais_sel = total_canais
    with c2:
        if st.button("Limpar (Canais)", use_container_width=True):
            canais_sel = []

    focus_prospec = st.checkbox(
        "Focar apenas em Prospecção Ativa (gráficos por vendedora)",
        value=False,
    )

# Aplicar filtros
df_filtrado = df.copy()
if "Criado" in df_filtrado.columns:
    df_filtrado = df_filtrado[
        (df_filtrado["Criado"].dt.normalize() >= pd.to_datetime(d_ini))
        & (df_filtrado["Criado"].dt.normalize() <= pd.to_datetime(d_fim))
    ]
if vendedores_sel:
    df_filtrado = df_filtrado[df_filtrado["Responsável"].isin(vendedores_sel)]
if canais_sel:
    df_filtrado = df_filtrado[df_filtrado["Canal de Origem"].isin(canais_sel)]


# -----------------------------
# Visão Geral (após filtros)
# -----------------------------
st.markdown("### 📊 Visão Geral (após filtros)")

# KPIs com tolerância a variações de rótulos e coluna
phase_series_list = []
for col in ["_fase_norm", "Fase"]:
    if col in df_filtrado.columns:
        phase_series_list.append(df_filtrado[col].astype(str).str.strip())

def match_any(options: set) -> pd.Series:
    if not phase_series_list:
        return pd.Series(False, index=df_filtrado.index)
    mask = pd.Series(False, index=df_filtrado.index)
    for s in phase_series_list:
        mask = mask | s.isin(options)
    return mask

total_leads = int(len(df_filtrado))
total_reunioes = int(match_any(REUNIOES_OPTS).sum())
total_em_proposta = int(match_any(PROPOSTA_OPTS).sum())
total_vendas = int(match_any(VENDAS_OPTS).sum())

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown("**Leads (Total)**")
    st.markdown(f"<h2 style='margin-top:0'>{total_leads}</h2>", unsafe_allow_html=True)
with c2:
    st.markdown("**Reuniões (Total)**")
    st.markdown(f"<h2 style='margin-top:0'>{total_reunioes}</h2>", unsafe_allow_html=True)
with c3:
    st.markdown("**Em Proposta**")
    st.markdown(f"<h2 style='margin-top:0'>{total_em_proposta}</h2>", unsafe_allow_html=True)
with c4:
    st.markdown("**Vendas (Total)**")
    st.markdown(f"<h2 style='margin-top:0'>{total_vendas}</h2>", unsafe_allow_html=True)


# -----------------------------
# Canais — Leads por Canal
# -----------------------------
st.markdown("### 📉 Canais — Leads por Canal")
canal_count = (
    df_filtrado.groupby("Canal de Origem").size().rename("Leads").reset_index()
)
canal_count = canal_count.sort_values("Leads", ascending=False)

bar_canais = (
    alt.Chart(canal_count)
    .mark_bar()
    .encode(
        y=alt.Y("Canal de Origem:N", sort="-x", title="Canal de Origem"),
        x=alt.X("Leads:Q", title="Leads Recebidos"),
        tooltip=["Canal de Origem:N", "Leads:Q"],
        color=alt.value("#93c5fd"),
    )
    .properties(height=max(120, 28 * len(canal_count)))
)
st.altair_chart(bar_canais, use_container_width=True)


# -----------------------------
# Funil por Canal — empilhado 100% com ordem fixa e cores
# -----------------------------
st.markdown("### 🧱 Detalhamento por Fase (Canal de Origem)")
if df_filtrado.empty:
    st.info("Sem dados no período/seleção.")
else:
    tmp = (
        df_filtrado.assign(FasePlot=df_filtrado["_fase_norm"])
        .groupby(["Canal de Origem", "FasePlot"])
        .size()
        .rename("Qtd")
        .reset_index()
    )

    # garantir todas as fases para cada canal (preencher 0)
    canals = tmp["Canal de Origem"].unique().tolist()
    grid = pd.MultiIndex.from_product([canals, FASE_ORDER], names=["Canal de Origem", "FasePlot"])
    tmp = tmp.set_index(["Canal de Origem", "FasePlot"]).reindex(grid, fill_value=0).reset_index()

    # % por canal
    tmp["TotalCanal"] = tmp.groupby("Canal de Origem")["Qtd"].transform("sum").replace(0, 1)
    tmp["Pct"] = tmp["Qtd"] / tmp["TotalCanal"]

    chart = (
        alt.Chart(tmp)
        .mark_bar()
        .encode(
            y=alt.Y("Canal de Origem:N", sort=canals, title="Canal de Origem"),
            x=alt.X("Pct:Q", stack="normalize", title="%", axis=alt.Axis(format="%")),
            color=alt.Color(
                "FasePlot:N",
                sort=FASE_ORDER,
                scale=alt.Scale(domain=list(FASE_COLOR.keys()), range=list(FASE_COLOR.values())),
                legend=alt.Legend(title="Fase"),
            ),
            tooltip=[
                alt.Tooltip("Canal de Origem:N", title="Canal"),
                alt.Tooltip("FasePlot:N", title="Fase"),
                alt.Tooltip("Qtd:Q", title="Qtd"),
                alt.Tooltip("Pct:Q", title="% do canal", format=".0%"),
            ],
            order=alt.Order("FasePlot:N", sort="ascending"),
        )
    ).properties(height=max(160, 30 * len(canals)))
    st.altair_chart(chart, use_container_width=True)


# -----------------------------
# Funil detalhado por Vendedora (contagem absoluta)
# -----------------------------
st.markdown("### 👩‍💼 Funil detalhado por Vendedora")
df_v = df_filtrado.copy()
if focus_prospec:
    df_v = df_v[df_v["Canal de Origem"] == "Prospecção Ativa"]

if df_v.empty:
    st.info("Sem dados para as condições atuais.")
else:
    t = (
        df_v.assign(FasePlot=df_v["_fase_norm"])
        .groupby(["Responsável", "FasePlot"])
        .size()
        .rename("Qtd")
        .reset_index()
    )

    vends = sorted(t["Responsável"].dropna().unique().tolist())
    if not vends:
        st.info("Sem vendedoras com dados.")
    else:
        # preencher 0 para fases ausentes por vendedora
        grid = pd.MultiIndex.from_product([vends, FASE_ORDER], names=["Responsável", "FasePlot"])
        t = t.set_index(["Responsável", "FasePlot"]).reindex(grid, fill_value=0).reset_index()

        chart_v = (
            alt.Chart(t)
            .mark_bar()
            .encode(
                y=alt.Y("Responsável:N", sort=vends, title="Vendedora"),
                x=alt.X("Qtd:Q", title="Leads"),
                color=alt.Color(
                    "FasePlot:N",
                    sort=FASE_ORDER,
                    scale=alt.Scale(domain=list(FASE_COLOR.keys()), range=list(FASE_COLOR.values())),
                    legend=alt.Legend(title="Fase"),
                ),
                tooltip=["Responsável:N", "FasePlot:N", "Qtd:Q"],
                order=alt.Order("FasePlot:N", sort="ascending"),
            )
        ).properties(height=max(160, 30 * len(vends)))
        st.altair_chart(chart_v, use_container_width=True)


# -----------------------------
# Leads criados por dia (Total / Vendedora / Canal)
# -----------------------------
st.markdown("### 📅 Leads criados por dia")
detalhe = st.radio("Detalhar por", ["Total", "Vendedora", "Canal de Origem"], horizontal=True, key="detalhe_diario")
show_mm = st.checkbox("Mostrar média móvel", value=True, key="mm_toggle")
mm_window = st.slider("Janela da média móvel (dias)", 1, 14, 7, key="mm_diario", disabled=not show_mm)

base_daily = df_filtrado[df_filtrado["Criado"].notna()].copy()
if base_daily.empty:
    st.info("Nenhum lead com data de criação válida no intervalo/seleção atual.")
else:
    base_daily["Dia"] = base_daily["Criado"].dt.floor("D")
    all_days = full_dates(d_ini, d_fim)

    if detalhe == "Total":
        g = base_daily.groupby("Dia").size().rename("Leads").reset_index()
        g = all_days.merge(g, on="Dia", how="left").fillna({"Leads": 0})
        g = g.sort_values("Dia")
        if show_mm:
            g["MM"] = g["Leads"].rolling(mm_window, min_periods=1).mean()

        bars = alt.Chart(g).mark_bar().encode(
            x=alt.X("yearmonthdate(Dia):O", title="Dia", axis=alt.Axis(format="%d/%m")),
            y=alt.Y("Leads:Q", title="Leads"),
            tooltip=[alt.Tooltip("yearmonthdate(Dia):O", title="Dia"), alt.Tooltip("Leads:Q", title="Leads")],
        )
        labels = alt.Chart(g).mark_text(dy=-4, size=11).encode(
            x=alt.X("yearmonthdate(Dia):O"), y="Leads:Q", text="Leads:Q", color=alt.value("#ffffff")
        )
        chart = bars + labels
        if show_mm:
            line = alt.Chart(g).mark_line(strokeWidth=2, color="#10b981").encode(
                x=alt.X("yearmonthdate(Dia):O"),
                y=alt.Y("MM:Q", title="Média móvel"),
                tooltip=[alt.Tooltip("yearmonthdate(Dia):O", title="Dia"), alt.Tooltip("MM:Q", title="Média móvel")],
            )
            chart = chart + line

    elif detalhe == "Vendedora":
        cats = sorted(base_daily["Responsável"].dropna().unique().tolist())
        grid = all_days.assign(key=1)
        cats_df = pd.DataFrame({"Responsável": cats}).assign(key=1)
        cart = grid.merge(cats_df, on="key").drop(columns="key")

        g = base_daily.groupby(["Dia", "Responsável"]).size().rename("Leads").reset_index()
        g = cart.merge(g, on=["Dia", "Responsável"], how="left").fillna({"Leads": 0})
        g = g.sort_values(["Responsável", "Dia"])

        bars = alt.Chart(g).mark_bar().encode(
            x=alt.X("yearmonthdate(Dia):O", title="Dia", axis=alt.Axis(format="%d/%m"),
                    scale=alt.Scale(paddingInner=0.2, paddingOuter=0.05)),
            xOffset=alt.XOffset("Responsável:N", sort=cats),
            y=alt.Y("Leads:Q", title="Leads"),
            color=alt.Color("Responsável:N", sort=cats, legend=alt.Legend(title="Vendedora")),
            tooltip=[alt.Tooltip("yearmonthdate(Dia):O", title="Dia"),
                     alt.Tooltip("Responsável:N", title="Vendedora"),
                     alt.Tooltip("Leads:Q")],
        )
        labels = alt.Chart(g).mark_text(dy=-4, size=11).encode(
            x=alt.X("yearmonthdate(Dia):O"),
            xOffset=alt.XOffset("Responsável:N", sort=cats),
            y="Leads:Q",
            text="Leads:Q",
            color=alt.value("#ffffff"),
        )
        chart = bars + labels
        if show_mm:
            g["MM"] = g.groupby("Responsável")["Leads"].transform(
                lambda s: s.rolling(mm_window, min_periods=1).mean()
            )
            lines = alt.Chart(g).mark_line(strokeWidth=2).encode(
                x=alt.X("yearmonthdate(Dia):O"),
                y=alt.Y("MM:Q", title="Média móvel"),
                color=alt.Color("Responsável:N", sort=cats, legend=None),
            )
            chart = chart + lines

    else:  # Canal
        cats = sorted(base_daily["Canal de Origem"].dropna().unique().tolist())
        grid = all_days.assign(key=1)
        cats_df = pd.DataFrame({"Canal de Origem": cats}).assign(key=1)
        cart = grid.merge(cats_df, on="key").drop(columns="key")

        g = base_daily.groupby(["Dia", "Canal de Origem"]).size().rename("Leads").reset_index()
        g = cart.merge(g, on=["Dia", "Canal de Origem"], how="left").fillna({"Leads": 0})
        g = g.sort_values(["Canal de Origem", "Dia"])

        bars = alt.Chart(g).mark_bar().encode(
            x=alt.X("yearmonthdate(Dia):O", title="Dia", axis=alt.Axis(format="%d/%m"),
                    scale=alt.Scale(paddingInner=0.2, paddingOuter=0.05)),
            xOffset=alt.XOffset("Canal de Origem:N", sort=cats),
            y=alt.Y("Leads:Q", title="Leads"),
            color=alt.Color("Canal de Origem:N", sort=cats, legend=alt.Legend(title="Canal")),
            tooltip=[alt.Tooltip("yearmonthdate(Dia):O", title="Dia"),
                     alt.Tooltip("Canal de Origem:N", title="Canal"),
                     alt.Tooltip("Leads:Q")],
        )
        labels = alt.Chart(g).mark_text(dy=-4, size=11).encode(
            x=alt.X("yearmonthdate(Dia):O"),
            xOffset=alt.XOffset("Canal de Origem:N", sort=cats),
            y="Leads:Q",
            text="Leads:Q",
            color=alt.value("#ffffff"),
        )
        chart = bars + labels
        if show_mm:
            g["MM"] = g.groupby("Canal de Origem")["Leads"].transform(
                lambda s: s.rolling(mm_window, min_periods=1).mean()
            )
            lines = alt.Chart(g).mark_line(strokeWidth=2).encode(
                x=alt.X("yearmonthdate(Dia):O"),
                y=alt.Y("MM:Q", title="Média móvel"),
                color=alt.Color("Canal de Origem:N", sort=cats, legend=None),
            )
            chart = chart + lines

    st.altair_chart(chart.properties(height=380), use_container_width=True)


# -----------------------------
# (Opcional) Tabela de dados limpos
# -----------------------------
with st.expander("Dados Limpos (prévia)"):
    cols_show = ["Fase", "_fase_norm", "Responsável", "Nome do Negócio", "Fonte", "Canal de Origem", "Criado"]
    cols_show = [c for c in cols_show if c in df_filtrado.columns]
    st.dataframe(df_filtrado[cols_show].sort_values("Criado", na_position="last").reset_index(drop=True))
