# app.py
# ---------------------------------------------
# CRM Relatório KIT — Dashboard Streamlit
# ---------------------------------------------

import io
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ---------- Config visual ----------
st.set_page_config(
    page_title="Gerador de Relatório CRM",
    page_icon="📊",
    layout="wide",
)

# Paleta de cores para fases (ordem fixa que o cliente pediu)
FASERDER = [
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
FASE_COLORS = {
    "Em Atendimento":      "#f0c419",  # amarelo
    "Agendando Reunião":   "#4caf50",  # verde
    "Reuniões Agendadas":  "#2e7d32",  # verde escuro
    "Proposta e Negociação":"#81c784", # verde claro
    "Negócio Fechado":     "#1b5e20",  # verde bem escuro
    "Abaixo de R$500K":    "#ef9a9a",  # vermelho claro
    "Fora do Perfil":      "#e57373",
    "Sem Interesse":       "#ef5350",
    "Sem retorno":         "#d32f2f",
    "Outros/Perdido":      "#b71c1c",
}

# ---------- Funções utilitárias ----------
def norm(s: str) -> str:
    return s.strip().lower()

def try_read_csv(file):
    # Lê CSV de forma robusta: detecta separador, tenta diferentes encodings
    tries = [
        dict(sep=None, engine="python", encoding="utf-8"),
        dict(sep=None, engine="python", encoding="latin-1"),
        dict(sep=None, engine="python", encoding_errors="ignore"),
    ]
    last_err = None
    for kw in tries:
        try:
            return pd.read_csv(file, **kw)
        except Exception as e:
            last_err = e
    raise last_err

def montar_mapa_canais(serie_fonte: pd.Series) -> pd.Series:
    val = serie_fonte.astype(str).str.strip()

    # Normaliza variações
    m = pd.Series("Outros", index=val.index)

    m[val.str.fullmatch(r"(?i)site")] = "Google Ads"

    # MetaAds variações
    m[val.str.contains(r"(?i)facebook.*meta\s*ads|face.*meta", na=False)] = "Trafego Pago - Face"
    m[val.str.contains(r"(?i)instagram.*meta\s*ads|insta.*meta", na=False)] = "Trafego Pago - Insta"

    m[val.str.fullmatch(r"(?i)lp")] = "Impulsionamento Instagram"
    m[val.str.contains(r"(?i)whats", na=False)] = "Inbound"

    m[val.str.contains(r"(?i)prospec", na=False)] = "Prospecção Ativa"
    m[val.str.contains(r"(?i)indica", na=False)] = "Indicação"

    # Novo canal solicitado
    m[val.str.contains(r"(?i)base\s*clt\s*\/?\s*sec|base\s*clt|base\s*sec", na=False)] = "Base CLT/SEC"

    return m

def padronizar_fase(s: pd.Series) -> pd.Series:
    v = s.astype(str).str.strip().str.lower()
    out = pd.Series("Em Atendimento", index=v.index)

    def any_of(*subs):
        regex = "|".join([rf"(?i){x}" for x in subs])
        return v.str.contains(regex, na=False)

    # Mapeamentos
    out[any_of("agendando", "agendamento")] = "Agendando Reunião"
    out[any_of("reuni", "reunião", "reuniao")] = "Reuniões Agendadas"
    out[any_of("proposta", "negocia")] = "Proposta e Negociação"
    out[any_of("fechado", "ganho", "ganha")] = "Negócio Fechado"

    out[any_of("abaixo", "500k", "500 k")] = "Abaixo de R$500K"
    out[any_of("fora do perfil", "fora perfil")] = "Fora do Perfil"
    out[any_of("sem retorno", "nao respondeu", "não respondeu")] = "Sem retorno"
    out[any_of("sem interesse")] = "Sem Interesse"
    out[any_of("perdid", "perda", "outros")] = "Outros/Perdido"

    return pd.Categorical(out, categories=FASERDER, ordered=True)

def add_badge(title: str, value: int):
    st.markdown(
        f"""
        <div style="display:flex;flex-direction:column;gap:4px;padding:16px 18px;border-radius:12px;background:#121212;border:1px solid #2c2c2c;min-width:160px;">
          <div style="opacity:.8;font-size:14px;">{title}</div>
          <div style="font-size:40px;font-weight:700;line-height:1;">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def bar_horz_count(df, by, title):
    g = df.groupby(by).size().reset_index(name="Leads")
    g = g.sort_values("Leads", ascending=True)
    fig = px.bar(
        g, x="Leads", y=by, orientation="h",
        title=title, text="Leads"
    )
    fig.update_traces(marker_color="#86c5ff", textposition="outside")
    fig.update_layout(height=420, xaxis_title="Leads Recebidos", yaxis_title=None, margin=dict(l=10,r=10,b=10,t=50))
    st.plotly_chart(fig, use_container_width=True)

def stacked_by_phase(df, group_col, title):
    # Garante todas as fases com 0
    ct = (df
          .assign(_fase=df["Fase"].astype("category").cat.add_categories([c for c in FASERDER if c not in df["Fase"].cat.categories]))
          .groupby([group_col, "_fase"])
          .size()
          .reset_index(name="Qtd"))
    ct.rename(columns={"_fase": "Fase"}, inplace=True)

    # Ordena fase pela ordem fixa
    ct["Fase"] = pd.Categorical(ct["Fase"], categories=FASERDER, ordered=True)

    # Percentual por grupo
    total = ct.groupby(group_col)["Qtd"].transform("sum").replace(0, 1)
    ct["%"] = (ct["Qtd"] / total) * 100

    fig = px.bar(
        ct, y=group_col, x="%", color="Fase",
        color_discrete_map=FASE_COLORS,
        orientation="h", category_orders={"Fase": FASERDER},
        title=title, hover_data={"Qtd": True, "%": ":.1f"}
    )
    # Mostra contagem no hover ao invés de %
    fig.update_traces(hovertemplate="<b>%{y}</b><br>Fase: %{marker.color}<br>Qtd: %{customdata[0]}<extra></extra>")
    fig.update_layout(barmode="stack", height=520, margin=dict(l=10,r=10,b=10,t=60))
    st.plotly_chart(fig, use_container_width=True)

def funil_vendedora(df, title):
    ct = (df
          .assign(Fase=df["Fase"].astype("category"))
          .groupby(["Responsável", "Fase"])
          .size()
          .reset_index(name="Qtd"))
    # Garante presença de todas as fases
    ct["Fase"] = pd.Categorical(ct["Fase"], categories=FASERDER, ordered=True)
    fig = px.bar(
        ct, x="Qtd", y="Responsável", color="Fase", orientation="h",
        color_discrete_map=FASE_COLORS, category_orders={"Fase": FASERDER},
        title=title
    )
    fig.update_layout(barmode="stack", height=520, margin=dict(l=10,r=10,b=10,t=60))
    st.plotly_chart(fig, use_container_width=True)

def leads_por_dia(df, detail: str, show_ma: bool, ma_win: int):
    df = df.copy()
    df["Dia"] = df["Criado"].dt.floor("D")

    if df["Dia"].isna().all():
        st.info("Não há datas válidas em 'Criado' após filtros.")
        return

    min_d, max_d = df["Dia"].min(), df["Dia"].max()
    full_idx = pd.date_range(min_d, max_d, freq="D")

    if detail == "Total":
        g = df.groupby("Dia").size().reindex(full_idx, fill_value=0)
        fig = px.bar(
            x=g.index, y=g.values, labels={"x":"Dia","y":"Leads"},
            title="📅 Leads criados por dia"
        )
        if show_ma:
            mav = pd.Series(g.values).rolling(ma_win, min_periods=1).mean().values
            fig.add_scatter(x=g.index, y=mav, mode="lines+markers", name=f"Média móvel ({ma_win})")
        st.plotly_chart(fig, use_container_width=True)

    elif detail == "Vendedora":
        g = df.groupby(["Dia", "Responsável"]).size().unstack(fill_value=0)
        g = g.reindex(full_idx, fill_value=0)
        fig = px.bar(
            g.reset_index().melt(id_vars="index", var_name="Vendedora", value_name="Leads"),
            x="index", y="Leads", color="Vendedora", barmode="group",
            title="📅 Leads criados por dia — por Vendedora"
        )
        fig.update_xaxes(title="Dia")
        if show_ma:
            # Média móvel do total (soma das vendedoras)
            total = g.sum(axis=1)
            mav = total.rolling(ma_win, min_periods=1).mean()
            fig.add_scatter(x=total.index, y=mav, mode="lines+markers", name=f"Média móvel ({ma_win})")
        st.plotly_chart(fig, use_container_width=True)

    else:  # Canal de Origem
        g = df.groupby(["Dia", "Canal de Origem"]).size().unstack(fill_value=0)
        g = g.reindex(full_idx, fill_value=0)
        fig = px.bar(
            g.reset_index().melt(id_vars="index", var_name="Canal de Origem", value_name="Leads"),
            x="index", y="Leads", color="Canal de Origem", barmode="group",
            title="📅 Leads criados por dia — por Canal de Origem"
        )
        fig.update_xaxes(title="Dia")
        if show_ma:
            total = g.sum(axis=1)
            mav = total.rolling(ma_win, min_periods=1).mean()
            fig.add_scatter(x=total.index, y=mav, mode="lines+markers", name=f"Média móvel ({ma_win})")
        st.plotly_chart(fig, use_container_width=True)

# ---------- UI - Upload ----------
st.title("Gerador de Relatório CRM")
uploaded = st.file_uploader("CSV do CRM", type=["csv"], help="Envie o CSV exportado do CRM")

if not uploaded:
    st.info("Envie um CSV para começar.")
    st.stop()

# ---------- Leitura robusta ----------
base_df = try_read_csv(uploaded)

# ---------- Escolha única de colunas (garante 1:1) ----------
cols = list(base_df.columns)
def find_cols(predicate):
    return [c for c in cols if predicate(norm(c))]

fase_cols     = find_cols(lambda cl: "fase" in cl)
resp_cols     = find_cols(lambda cl: "respons" in cl)
negocio_cols  = find_cols(lambda cl: "negócio" in cl or "negocio" in cl or "nome do negócio" in cl)
fonte_cols    = find_cols(lambda cl: "fonte" in cl)
criado_cols   = find_cols(lambda cl: "criado" in cl or "criação" in cl or "criacao" in cl or "data de criação" in cl)
motivo_cols   = [c for c in cols if "motivo" in norm(c) and "perd" in norm(c)]

col_map = {}
if fase_cols:    col_map[fase_cols[0]]    = "Fase"
if resp_cols:    col_map[resp_cols[0]]    = "Responsável"
if negocio_cols: col_map[negocio_cols[0]] = "Nome do Negócio"
if fonte_cols:   col_map[fonte_cols[0]]   = "Fonte"
if criado_cols:  col_map[criado_cols[0]]  = "Criado"
if motivo_cols:  col_map[motivo_cols[-1]] = "Motivo de perda"  # usa a "segunda"/última, como combinado

if not col_map:
    st.error("Não consegui identificar as colunas necessárias no CSV.")
    st.stop()

df = base_df[list(col_map.keys())].rename(columns=col_map).copy()

# Datas
if "Criado" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["Criado"]):
    df["Criado"] = pd.to_datetime(df["Criado"].astype(str), errors="coerce")

# Padronizações
if "Fase" in df.columns:
    df["Fase"] = padronizar_fase(df["Fase"])
else:
    df["Fase"] = pd.Categorical(["Em Atendimento"]*len(df), categories=FASERDER, ordered=True)

df["Canal de Origem"] = montar_mapa_canais(df.get("Fonte", pd.Series(index=df.index, dtype=str)))

# ---------- Filtros ----------
with st.expander("Filtros", expanded=True):
    # Período
    min_d = df["Criado"].min() if "Criado" in df else pd.Timestamp.today() - pd.Timedelta(days=30)
    max_d = df["Criado"].max() if "Criado" in df else pd.Timestamp.today()
    if pd.isna(min_d) or pd.isna(max_d):
        min_d = pd.Timestamp.today() - pd.Timedelta(days=30)
        max_d = pd.Timestamp.today()
    col1, col2 = st.columns([1,3])
    with col1:
        st.caption("Período (Criado)")
    with col2:
        date_range = st.date_input(
            "", value=(min_d.date(), max_d.date()),
            min_value=min_d.date(), max_value=max_d.date(), format="YYYY/MM/DD"
        )

    # Vendedoras
    vend_list = sorted(df["Responsável"].dropna().astype(str).unique())
    st.caption("Vendedoras")
    c1, c2 = st.columns([6,1])
    with c1:
        vend_sel = st.multiselect(
            "", vend_list, default=vend_list,
            placeholder="Selecione as vendedoras"
        )
    with c2:
        if st.button("Todos", use_container_width=True):
            vend_sel = vend_list
        if st.button("Limpar", use_container_width=True):
            vend_sel = []

    # Canais
    canal_list = [
        "Google Ads", "Trafego Pago - Face", "Trafego Pago - Insta",
        "Impulsionamento Instagram", "Prospecção Ativa", "Inbound",
        "Indicação", "Base CLT/SEC", "Outros"
    ]
    st.caption("Canais de Origem")
    c3, c4 = st.columns([6,1])
    with c3:
        canal_sel = st.multiselect("", canal_list, default=canal_list, placeholder="Selecione canais")
    with c4:
        if st.button("Todos  ", key="c_all", use_container_width=True):
            canal_sel = canal_list
        if st.button("Limpar ", key="c_clr", use_container_width=True):
            canal_sel = []

# Aplicar filtros
df_filtrado = df.copy()
if "Criado" in df_filtrado.columns and isinstance(date_range, tuple) and len(date_range) == 2:
    ini, fim = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    df_filtrado = df_filtrado[df_filtrado["Criado"].between(ini, fim)]

if vend_sel:
    df_filtrado = df_filtrado[df_filtrado["Responsável"].astype(str).isin(vend_sel)]
else:
    df_filtrado = df_filtrado.iloc[:0]  # vazio

if canal_sel:
    df_filtrado = df_filtrado[df_filtrado["Canal de Origem"].astype(str).isin(canal_sel)]
else:
    df_filtrado = df_filtrado.iloc[:0]

st.markdown("### 📊 Visão Geral (após filtros)")
k1, k2, k3, k4 = st.columns(4)

total_leads = len(df_filtrado)
total_reunioes = (df_filtrado["Fase"].isin(["Agendando Reunião", "Reuniões Agendadas"])).sum()
total_proposta = (df_filtrado["Fase"] == "Proposta e Negociação").sum()
total_vendas = (df_filtrado["Fase"] == "Negócio Fechado").sum()

with k1: add_badge("Leads (Total)", int(total_leads))
with k2: add_badge("Reuniões (Total)", int(total_reunioes))
with k3: add_badge("Em Proposta", int(total_proposta))
with k4: add_badge("Vendas (Total)", int(total_vendas))

st.divider()

# ---------- Gráficos ----------
colA, = st.columns(1)
with colA:
    bar_horz_count(df_filtrado, "Canal de Origem", "📈 Canais — Leads por Canal")

st.divider()

# Detalhamento por canal (stacked por fase)
stacked_by_phase(df_filtrado, "Canal de Origem", "📊 Detalhamento das Fases por Canal de Origem")

st.divider()

# Funil detalhado por vendedora (stacked, eixo horizontal em quantidade)
funil_vendedora(df_filtrado, "🧑‍💼 Funil detalhado por Vendedora")

st.divider()

# Leads por dia (Total / Vendedora / Canal) com média móvel opcional
st.markdown("### 📅 Leads criados por dia")
copt1, copt2, copt3 = st.columns([2,3,3])
with copt1:
    detail = st.radio("Detalhar por", ["Total", "Vendedora", "Canal de Origem"], horizontal=True, index=1)
with copt2:
    show_ma = st.checkbox("Mostrar média móvel", value=False)
with copt3:
    ma_win = st.slider("Janela da média móvel (dias)", 2, 30, 7) if show_ma else 7

leads_por_dia(df_filtrado, detail, show_ma, ma_win)

st.caption("Dica: use os filtros acima para isolar vendedoras, canais e período.")
