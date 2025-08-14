# app.py — Relatório CRM — v9
# - Gráfico "Leads por dia" com barras lado-a-lado (Vendedora/Canal) + labels + toggle de média móvel
# - Filtros com UX melhor (Todos/Limpar + atalhos)
# - Gráficos/tabelas por vendedora respeitam filtros de canal (toggle opcional só Prospecção)
# - Ordem/cores fixas nos gráficos de fases
# - Canal "Base CLT/SEC" incluído

import streamlit as st
import pandas as pd
import unicodedata
import altair as alt
from io import BytesIO
from datetime import datetime, date
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(page_title="Relatório CRM — v9", layout="wide")
st.title("Gerador de Relatório CRM — v9 (Gráficos + Filtros + PDF)")
st.caption("Envie o CSV do CRM (separador ';' ou ','). O app detecta o separador e o encoding automaticamente.")

# =========================================================
# Helpers
# =========================================================
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def norm_phase(s):
    if pd.isna(s):
        return ""
    s = str(s).strip().lower()
    s = strip_accents(s)
    s = (
        s.replace("r$", "")
        .replace("  ", " ")
        .replace("–", "-")
        .replace("—", "-")
        .replace(" -", "")
        .replace("-", " ")
    )
    return " ".join(s.split())

def norm_text(x):
    return strip_accents(str(x).strip().lower()) if pd.notna(x) else ""

def pct(a, b):
    return round((a / b * 100) if b else 0, 2)

def count_set(series_norm, allowed_set):
    return series_norm.isin(allowed_set).sum()

def read_crm_csv(uploaded_file) -> pd.DataFrame:
    """Leitor robusto:
      - detecta encoding (utf-8/latin1)
      - detecta delimitador (;/,)
      - ignora linhas ruins (on_bad_lines='skip')
    """
    raw = uploaded_file.getvalue()

    # encoding
    enc_used = "utf-8"
    for enc in ("utf-8", "latin1"):
        try:
            _ = raw.decode(enc, errors="strict")
            enc_used = enc
            break
        except Exception:
            continue
    text = raw.decode(enc_used, errors="ignore")

    # delimitador
    sample = "\n".join(text.splitlines()[:20])
    delim = ";" if sample.count(";") >= sample.count(",") else ","

    return pd.read_csv(
        BytesIO(raw),
        sep=delim,
        engine="python",
        encoding=enc_used,
        on_bad_lines="skip",
        dtype_backend="numpy_nullable",
    )

# =========================================================
# Upload
# =========================================================
up = st.file_uploader("CSV do CRM", type=["csv"])
if up is None:
    st.info("⬆️ Envie um CSV para começar.")
    st.stop()

# =========================================================
# Carrega dados
# =========================================================
try:
    df_raw = read_crm_csv(up)
except Exception as e:
    st.error(f"Não consegui ler o CSV. Detalhe: {e}")
    st.stop()

# Normaliza nomes esperados (mantendo a segunda 'Motivo de perda')
expected = {
    "Fase": ["Fase"],
    "Responsável": ["Responsável", "Responsavel"],
    "Nome do Negócio": ["Nome do Negócio", "Nome do negocio", "Nome do negócio"],
    "Fonte": ["Fonte"],
    "Criado": ["Criado", "Data de criação", "Data de criacao"],
    "Motivo de perda": ["Motivo de perda.1", "Motivo de perda_1", "Motivo de perda 1"],
}

colmap = {}
for wanted, candidates in expected.items():
    for c in candidates:
        if c in df_raw.columns:
            colmap[wanted] = c
            break

missing = [k for k in expected.keys() if k not in colmap]
if missing:
    st.error(f"Faltam colunas obrigatórias no CSV: {missing}\n\nColunas recebidas: {list(df_raw.columns)}")
    st.stop()

df = df_raw[[colmap[k] for k in expected.keys()]].copy()
df.columns = list(expected.keys())

# Tipos e normalizações
df["Criado"] = pd.to_datetime(df["Criado"], errors="coerce", dayfirst=True)
df["_fase_norm"] = df["Fase"].apply(norm_phase)

# =========================================================
# Mapeamento "Fonte" -> "Canal de Origem" (inclui Base CLT/SEC)
# =========================================================
map_dict = {
    "site": "Google Ads",
    "face - metaads": "Trafego Pago - Face",
    "facebook- meta ads": "Trafego Pago - Face",
    "facebook - meta ads": "Trafego Pago - Face",
    "facebook- metaads": "Trafego Pago - Face",
    "facebook meta ads": "Trafego Pago - Face",
    "insta - metaads": "Trafego Pago - Insta",
    "instagram - meta ads": "Trafego Pago - Insta",
    "instagram- meta ads": "Trafego Pago - Insta",
    "instagram meta ads": "Trafego Pago - Insta",
    "lp": "Impulsionamento Instagram",
    "prospeccao ativa": "Prospecção Ativa",
    "prospecção ativa": "Prospecção Ativa",
    "whatsapp": "Inbound",
    "indicacao": "Indicação",
    "indicação": "Indicação",
    "base clt/sec": "Base CLT/SEC",
    "base clt sec": "Base CLT/SEC",
}
df["Canal de Origem"] = df["Fonte"].apply(lambda x: map_dict.get(norm_text(x), "Outros"))

canal_ordem = [
    "Google Ads",
    "Trafego Pago - Face",
    "Trafego Pago - Insta",
    "Impulsionamento Instagram",
    "Prospecção Ativa",
    "Inbound",
    "Indicação",
    "Base CLT/SEC",
    "Outros",
]

# =========================================================
# Filtros (UX melhorado)
# =========================================================
st.sidebar.header("Filtros")

def multi_select_with_buttons(label, options, default_all=True, key=""):
    if default_all:
        default = options
    else:
        default = []
    if key not in st.session_state:
        st.session_state[key] = default

    cols = st.sidebar.columns([3, 1, 1])
    with cols[0]:
        sel = st.multiselect(label, options=options, default=st.session_state[key], key=f"ms_{key}")
    with cols[1]:
        if st.button("Todos", key=f"all_{key}"):
            st.session_state[key] = options
            st.rerun()
    with cols[2]:
        if st.button("Limpar", key=f"clear_{key}"):
            st.session_state[key] = []
            st.rerun()

    st.session_state[key] = st.session_state[f"ms_{key}"]
    return st.session_state[key]

# período
min_d = pd.to_datetime(df["Criado"].min()).date() if df["Criado"].notna().any() else date.today()
max_d = pd.to_datetime(df["Criado"].max()).date() if df["Criado"].notna().any() else date.today()
d_ini, d_fim = st.sidebar.date_input("Período (Criado)", value=(min_d, max_d))
if isinstance(d_ini, tuple):
    d_ini, d_fim = d_ini

# vendedoras
vendedoras = sorted(df["Responsável"].dropna().unique().tolist())
sel_vendedoras = multi_select_with_buttons("Vendedoras", vendedoras, default_all=True, key="vendedoras")

# canais (ordenados + extras)
canais = [c for c in canal_ordem if c in df["Canal de Origem"].unique()] + sorted(
    [c for c in df["Canal de Origem"].unique() if c not in canal_ordem]
)

# atalhos
canais_mkt = ["Google Ads", "Trafego Pago - Face", "Trafego Pago - Insta", "Impulsionamento Instagram", "Inbound"]
c1, c2, c3 = st.sidebar.columns(3)
if c1.button("Somente Mkt"):
    st.session_state["canais"] = [c for c in canais if c in canais_mkt]
    st.rerun()
if c2.button("Somente Prospecção"):
    st.session_state["canais"] = [c for c in canais if c == "Prospecção Ativa"]
    st.rerun()
if c3.button("Exceto Outros"):
    st.session_state["canais"] = [c for c in canais if c != "Outros"]
    st.rerun()

sel_canais = multi_select_with_buttons("Canais de Origem", canais, default_all=True, key="canais")

# toggle: focar apenas Prospecção Ativa para os gráficos por vendedora
only_prospec = st.sidebar.checkbox("Focar apenas em Prospecção Ativa (gráficos por vendedora)", value=False)

# aplica filtros
mask = pd.Series(True, index=df.index)
if df["Criado"].notna().any():
    mask &= df["Criado"].dt.date.between(d_ini, d_fim)
if sel_vendedoras:
    mask &= df["Responsável"].isin(sel_vendedoras)
if sel_canais:
    mask &= df["Canal de Origem"].isin(sel_canais)

df = df[mask].copy()
base_vendedora_df = df if not only_prospec else df[df["Canal de Origem"] == "Prospecção Ativa"]

# =========================================================
# Labels / Conjuntos de fases
# =========================================================
label_perdidos = {
    "Sem retorno": {"sem retorno"},
    "Sem Interesse": {"sem interesse"},
    "Fora do Perfil": {"fora do perfil"},
    "Outros/Perdido": {"outros / perdido", "outros/perdido", "outros perdido"},
    "Abaixo de R$500K": {"abaixo de 500k", "abaixo de r$500k", "abaixo de 500 k", "abaixo de 500 mil"},
}
labels_reuniao_agendando = {"agendando reuniao", "agendamento de reuniao"}
labels_reuniao_agendada = {"reuniao agendada", "reunioes agendadas"}
labels_reuniao_all = labels_reuniao_agendando | labels_reuniao_agendada
labels_proposta = {"proposta e negociacao"}
labels_venda = {"negocio fechado", "negocios fechados"}

# =========================================================
# Tabelas por canal
# =========================================================
# 1) Funil Comercial do Período
funil_rows = []
for canal in canal_ordem:
    g = df[df["Canal de Origem"] == canal]
    total = len(g)
    row = {"Canal de Origem": canal, "Leads Recebidos": total}
    for colname, variants in label_perdidos.items():
        row[colname] = count_set(g["_fase_norm"], variants)
    row["Agendando Reunião"] = count_set(g["_fase_norm"], labels_reuniao_agendando)
    row["Reuniões Agendadas"] = count_set(g["_fase_norm"], labels_reuniao_agendada)
    row["Proposta e Negociação"] = count_set(g["_fase_norm"], labels_proposta)
    row["Negócio Fechado"] = count_set(g["_fase_norm"], labels_venda)
    anteriores = sum(v for k, v in row.items() if k not in {"Canal de Origem", "Leads Recebidos"})
    row["Em Atendimento"] = max(total - anteriores, 0)
    funil_rows.append(row)

funil_df = pd.DataFrame(funil_rows)
expected_cols = [
    "Canal de Origem",
    "Leads Recebidos",
    "Sem retorno",
    "Sem Interesse",
    "Fora do Perfil",
    "Outros/Perdido",
    "Abaixo de R$500K",
    "Agendando Reunião",
    "Reuniões Agendadas",
    "Proposta e Negociação",
    "Negócio Fechado",
    "Em Atendimento",
]
for c in expected_cols:
    if c not in funil_df.columns:
        funil_df[c] = 0
funil_df = funil_df[expected_cols]

total_row = {"Canal de Origem": "TOTAL"}
for c in expected_cols[1:]:
    total_row[c] = funil_df[c].sum()
funil_df = pd.concat([funil_df, pd.DataFrame([total_row])], ignore_index=True)

# 2) Conversões por Canal
conv_rows = []
for canal in canal_ordem:
    g = df[df["Canal de Origem"] == canal]
    leads = len(g)
    reunioes = count_set(g["_fase_norm"], labels_reuniao_all)
    vendas = count_set(g["_fase_norm"], labels_venda)
    conv_rows.append(
        {
            "Canal de Origem": canal,
            "% Reuniões/Leads": pct(reunioes, leads),
            "% Vendas/Leads": pct(vendas, leads),
            "% Vendas/Reuniões": pct(vendas, reunioes),
        }
    )

leads_tot = len(df)
reunioes_tot = count_set(df["_fase_norm"], labels_reuniao_all)
vendas_tot = count_set(df["_fase_norm"], labels_venda)
conv_rows.append(
    {
        "Canal de Origem": "TOTAL",
        "% Reuniões/Leads": pct(reunioes_tot, leads_tot),
        "% Vendas/Leads": pct(vendas_tot, leads_tot),
        "% Vendas/Reuniões": pct(vendas_tot, reunioes_tot),
    }
)
conv_df = pd.DataFrame(conv_rows)

# =========================================================
# Tabelas/Agregações por Vendedora (respeitando filtros de canal)
# =========================================================
todas_vendedoras = sorted(base_vendedora_df["Responsável"].dropna().unique().tolist())

# 3) Resumo por Vendedora
prospec = base_vendedora_df
prospec_rows = []
for resp in todas_vendedoras:
    g = prospec[prospec["Responsável"] == resp]
    leads = len(g)
    reunioes = count_set(g["_fase_norm"], labels_reuniao_all)
    vendas = count_set(g["_fase_norm"], labels_venda)
    prospec_rows.append(
        {
            "Vendedora": resp,
            "Leads Gerados": leads,
            "Reuniões Agendadas": reunioes,
            "Vendas": vendas,
            "Conversão Reunião (%)": pct(reunioes, leads),
            "Conversão Venda (%)": pct(vendas, leads),
        }
    )
prospec_rows.append(
    {
        "Vendedora": "TOTAL",
        "Leads Gerados": len(prospec),
        "Reuniões Agendadas": count_set(prospec["_fase_norm"], labels_reuniao_all),
        "Vendas": count_set(prospec["_fase_norm"], labels_venda),
        "Conversão Reunião (%)": pct(count_set(prospec["_fase_norm"], labels_reuniao_all), len(prospec)) if len(prospec) else 0,
        "Conversão Venda (%)": pct(count_set(prospec["_fase_norm"], labels_venda), len(prospec)) if len(prospec) else 0,
    }
)
prospec_resumo_df = pd.DataFrame(prospec_rows)

# 4) Funil detalhado por Vendedora (tabela)
prospec_funil_rows = []
for resp in todas_vendedoras:
    g = base_vendedora_df[base_vendedora_df["Responsável"] == resp]
    row = {"Vendedora": resp, "Leads Gerados (base filtrada)": len(g)}
    row["Sem retorno"] = count_set(g["_fase_norm"], {"sem retorno"})
    row["Sem Interesse"] = count_set(g["_fase_norm"], {"sem interesse"})
    row["Fora do Perfil"] = count_set(g["_fase_norm"], {"fora do perfil"})
    row["Outros/Perdido"] = count_set(g["_fase_norm"], {"outros / perdido", "outros/perdido", "outros perdido"})
    row["Abaixo de R$500K"] = count_set(g["_fase_norm"], {"abaixo de 500k", "abaixo de r$500k", "abaixo de 500 k", "abaixo de 500 mil"})
    row["Agendando Reunião"] = count_set(g["_fase_norm"], {"agendando reuniao", "agendamento de reuniao"})
    row["Reuniões Agendadas"] = count_set(g["_fase_norm"], {"reuniao agendada", "reunioes agendadas"})
    row["Proposta e Negociação"] = count_set(g["_fase_norm"], {"proposta e negociacao"})
    row["Negócio Fechado"] = count_set(g["_fase_norm"], {"negocio fechado", "negocios fechados"})
    anteriores = sum(row[k] for k in [
        "Sem retorno","Sem Interesse","Fora do Perfil","Outros/Perdido","Abaixo de R$500K",
        "Agendando Reunião","Reuniões Agendadas","Proposta e Negociação","Negócio Fechado"
    ])
    row["Em Atendimento"] = max(row["Leads Gerados (base filtrada)"] - anteriores, 0)
    prospec_funil_rows.append(row)
prospec_funil_df = pd.DataFrame(prospec_funil_rows)
if not prospec_funil_df.empty:
    tot = {"Vendedora": "TOTAL"}
    for c in prospec_funil_df.columns:
        if c != "Vendedora":
            tot[c] = prospec_funil_df[c].sum()
    prospec_funil_df = pd.concat([prospec_funil_df, pd.DataFrame([tot])], ignore_index=True)

# 5) Resumo por Vendedora × Origem (Mkt vs Prospecção)
vend_origem_rows = []
for resp in sorted(df["Responsável"].dropna().unique()):
    g = df[df["Responsável"] == resp]
    for origem, mask in {
        "Prospecção Ativa": g["Canal de Origem"].eq("Prospecção Ativa"),
        "Leads de Mkt": g["Canal de Origem"].isin(["Google Ads","Trafego Pago - Face","Trafego Pago - Insta","Impulsionamento Instagram","Inbound"]),
    }.items():
        sub = g[mask]
        leads = len(sub)
        reunioes = count_set(sub["_fase_norm"], labels_reuniao_all)
        vendas = count_set(sub["_fase_norm"], labels_venda)
        vend_origem_rows.append(
            {
                "Vendedora": resp,
                "Origem do Lead": origem,
                "Leads Trabalhados": leads,
                "Reuniões Agendadas": reunioes,
                "Vendas": vendas,
                "Conversão Reunião (%)": pct(reunioes, leads),
                "Conversão Venda (%)": pct(vendas, leads),
            }
        )
vend_origem_df = pd.DataFrame(vend_origem_rows)

# =========================================================
# Dashboard / Gráficos (Altair)
# =========================================================
st.markdown("### 📊 Visão Geral (após filtros)")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Leads (Total)", len(df))
with col2:
    st.metric("Reuniões (Total)", int(count_set(df["_fase_norm"], labels_reuniao_all)))
with col3:
    st.metric("Vendas (Total)", int(count_set(df["_fase_norm"], labels_venda)))

# --- Gráfico 1: Leads por Canal
st.markdown("### 📈 Canais")
base = funil_df[funil_df["Canal de Origem"] != "TOTAL"][["Canal de Origem", "Leads Recebidos"]]
chart_leads = alt.Chart(base).mark_bar().encode(
    x="Leads Recebidos:Q", y=alt.Y("Canal de Origem:N", sort="-x")
)
st.altair_chart(chart_leads.properties(height=300), use_container_width=True)

# Paleta e ORDEM fixa das fases
phase_order = [
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
phase_colors = [
    "#fbbf24",  # Em Atendimento
    "#86efac",  # Agendando Reunião
    "#4ade80",  # Reuniões Agendadas
    "#22c55e",  # Proposta e Negociação
    "#16a34a",  # Negócio Fechado
    "#fca5a5",  # Abaixo de R$500K
    "#f87171",  # Fora do Perfil
    "#dc2626",  # Sem Interesse
    "#991b1b",  # Sem retorno
    "#ef4444",  # Outros/Perdido
]

# --- Gráfico 2: Fases x Canal (empilhado normalizado; tooltip = Quantidade)
fases_cols = [
    "Sem retorno","Sem Interesse","Fora do Perfil","Outros/Perdido","Abaixo de R$500K",
    "Agendando Reunião","Reuniões Agendadas","Proposta e Negociação","Negócio Fechado","Em Atendimento"
]
melt = funil_df[funil_df["Canal de Origem"] != "TOTAL"].melt(
    id_vars=["Canal de Origem"], value_vars=fases_cols, var_name="Fase", value_name="Qtd",
)
# índice para controlar a ordem de empilhamento
phase_rank = {name: i for i, name in enumerate(phase_order)}
melt["fase_ord"] = melt["Fase"].map(phase_rank).astype("int64")

chart_stack = (
    alt.Chart(melt)
    .mark_bar()
    .encode(
        x=alt.X("sum(Qtd):Q", stack="normalize", title="Proporção"),
        y=alt.Y("Canal de Origem:N", sort="-x"),
        color=alt.Color(
            "Fase:N",
            sort=phase_order,
            scale=alt.Scale(domain=phase_order, range=phase_colors),
            legend=alt.Legend(title="Fase")
        ),
        tooltip=[alt.Tooltip("Canal de Origem:N"), alt.Tooltip("Fase:N"), alt.Tooltip("sum(Qtd):Q", title="Quantidade")],
        order=alt.Order("fase_ord:Q", sort="ascending"),
    )
)
st.altair_chart(chart_stack.properties(height=350), use_container_width=True)

# --- Gráfico 3: Conversões por Canal
conv_melt = conv_df[conv_df["Canal de Origem"] != "TOTAL"].melt(
    id_vars=["Canal de Origem"], var_name="Métrica", value_name="Valor"
)
chart_conv = alt.Chart(conv_melt).mark_bar().encode(
    x=alt.X("Valor:Q", title="%"),
    y=alt.Y("Canal de Origem:N", sort="-x"),
    color="Métrica:N",
    tooltip=[alt.Tooltip("Canal de Origem:N"), alt.Tooltip("Métrica:N"), alt.Tooltip("Valor:Q", title="%")],
)
st.altair_chart(chart_conv.properties(height=280), use_container_width=True)

# --- Gráfico 4: Vendedoras — barras agrupadas (respeita filtros de canal)
st.markdown("### 👤 Vendedoras (respeita filtros de canal)")
base_v = prospec_resumo_df[prospec_resumo_df["Vendedora"] != "TOTAL"][["Vendedora", "Leads Gerados", "Reuniões Agendadas", "Vendas"]]
chart_v = alt.Chart(base_v).transform_fold(
    ["Leads Gerados", "Reuniões Agendadas", "Vendas"], as_=["Métrica", "Valor"]
).mark_bar().encode(
    x="Valor:Q",
    y=alt.Y("Vendedora:N", sort="-x"),
    color="Métrica:N",
    tooltip=[alt.Tooltip("Vendedora:N"), alt.Tooltip("Métrica:N"), alt.Tooltip("Valor:Q", title="Quantidade")],
)
st.altair_chart(chart_v.properties(height=300), use_container_width=True)

# --- Gráfico 5: Funil detalhado por Vendedora (quantidade; respeita filtros de canal)
st.markdown("### 📊 Funil detalhado por Vendedora")
if not prospec_funil_df.empty:
    pf_plot = prospec_funil_df[prospec_funil_df["Vendedora"] != "TOTAL"].copy()
    fases_plot = [
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
    for col in fases_plot:
        if col not in pf_plot.columns:
            pf_plot[col] = 0

    melted_v = pf_plot.melt(id_vars=["Vendedora"], value_vars=fases_plot, var_name="Fase", value_name="Qtd")
    melted_v["fase_ord"] = melted_v["Fase"].map(phase_rank).astype("int64")

    chart_pf = (
        alt.Chart(melted_v)
        .mark_bar()
        .encode(
            x=alt.X("sum(Qtd):Q", stack="zero", title="Quantidade"),
            y=alt.Y("Vendedora:N", sort="-x"),
            color=alt.Color("Fase:N", sort=phase_order, scale=alt.Scale(domain=phase_order, range=phase_colors),
                            legend=alt.Legend(title="Fase")),
            tooltip=[alt.Tooltip("Vendedora:N"), alt.Tooltip("Fase:N"), alt.Tooltip("sum(Qtd):Q", title="Quantidade")],
            order=alt.Order("fase_ord:Q", sort="ascending"),
        )
        .properties(height=320)
    )
    st.altair_chart(chart_pf, use_container_width=True)

# --- Gráfico 6: Leads criados por dia (respeita todos os filtros)
st.markdown("### 📅 Leads criados por dia")
detalhe = st.radio("Detalhar por", ["Total", "Vendedora", "Canal de Origem"], horizontal=True, key="detalhe_diario")

# Toggle de média móvel
show_mm = st.checkbox("Mostrar média móvel", value=True, key="mm_toggle")
mm_window = st.slider("Janela da média móvel (dias)", 1, 14, 7, key="mm_diario", disabled=not show_mm)

base_daily = df[df["Criado"].notna()].copy()
if base_daily.empty:
    st.info("Nenhum lead com data de criação válida no intervalo/seleção atual.")
else:
    base_daily["Dia"] = base_daily["Criado"].dt.floor("D")

    if detalhe == "Total":
        g = base_daily.groupby("Dia").size().rename("Leads").reset_index().sort_values("Dia")
        if show_mm:
            g["MM"] = g["Leads"].rolling(mm_window, min_periods=1).mean()

        bars = alt.Chart(g).mark_bar().encode(
            x=alt.X("Dia:T", title="Dia", axis=alt.Axis(format="%d/%m")),
            y=alt.Y("Leads:Q", title="Leads"),
            tooltip=[alt.Tooltip("Dia:T", title="Dia", format="%d/%m/%Y"),
                     alt.Tooltip("Leads:Q", title="Leads")],
        )
        labels = alt.Chart(g).mark_text(dy=-4, size=11).encode(
            x="Dia:T", y="Leads:Q", text="Leads:Q", color=alt.value("#ffffff")
        )
        chart = bars + labels
        if show_mm:
            line = alt.Chart(g).mark_line(strokeWidth=2, color="#10b981").encode(
                x="Dia:T", y=alt.Y("MM:Q", title="Média móvel"),
                tooltip=[alt.Tooltip("Dia:T", title="Dia", format="%d/%m/%Y"),
                         alt.Tooltip("MM:Q", title="Média móvel")],
            )
            chart = chart + line

    elif detalhe == "Vendedora":
        g = (
            base_daily.groupby(["Dia", "Responsável"])
            .size().rename("Leads").reset_index().sort_values(["Responsável", "Dia"])
        )
        ordem_v = sorted(g["Responsável"].unique().tolist())

        bars = alt.Chart(g).mark_bar().encode(
            x=alt.X("Dia:T", title="Dia", axis=alt.Axis(format="%d/%m"),
                    scale=alt.Scale(paddingInner=0.2, paddingOuter=0.05)),
            xOffset=alt.XOffset("Responsável:N", sort=ordem_v),
            y=alt.Y("Leads:Q", title="Leads"),
            color=alt.Color("Responsável:N", sort=ordem_v, legend=alt.Legend(title="Vendedora")),
            tooltip=[alt.Tooltip("Dia:T", title="Dia", format="%d/%m/%Y"),
                     alt.Tooltip("Responsável:N", title="Vendedora"),
                     alt.Tooltip("Leads:Q", title="Leads")],
        )
        labels = alt.Chart(g).mark_text(dy=-4, size=11).encode(
            x=alt.X("Dia:T"),
            xOffset=alt.XOffset("Responsável:N", sort=ordem_v),
            y="Leads:Q",
            text="Leads:Q",
            color=alt.value("#ffffff"),
        )
        chart = bars + labels

        if show_mm:
            g["MM"] = g.groupby("Responsável")["Leads"].transform(lambda s: s.rolling(mm_window, min_periods=1).mean())
            lines = alt.Chart(g).mark_line(strokeWidth=2).encode(
                x="Dia:T",
                y=alt.Y("MM:Q", title="Média móvel"),
                color=alt.Color("Responsável:N", sort=ordem_v, legend=None),
            )
            chart = chart + lines

    else:  # detalhe == "Canal de Origem"
        g = (
            base_daily.groupby(["Dia", "Canal de Origem"])
            .size().rename("Leads").reset_index().sort_values(["Canal de Origem", "Dia"])
        )
        ordem_c = sorted(g["Canal de Origem"].unique().tolist())

        bars = alt.Chart(g).mark_bar().encode(
            x=alt.X("Dia:T", title="Dia", axis=alt.Axis(format="%d/%m"),
                    scale=alt.Scale(paddingInner=0.2, paddingOuter=0.05)),
            xOffset=alt.XOffset("Canal de Origem:N", sort=ordem_c),
            y=alt.Y("Leads:Q", title="Leads"),
            color=alt.Color("Canal de Origem:N", sort=ordem_c, legend=alt.Legend(title="Canal")),
            tooltip=[alt.Tooltip("Dia:T", title="Dia", format="%d/%m/%Y"),
                     alt.Tooltip("Canal de Origem:N", title="Canal"),
                     alt.Tooltip("Leads:Q", title="Leads")],
        )
        labels = alt.Chart(g).mark_text(dy=-4, size=11).encode(
            x=alt.X("Dia:T"),
            xOffset=alt.XOffset("Canal de Origem:N", sort=ordem_c),
            y="Leads:Q",
            text="Leads:Q",
            color=alt.value("#ffffff"),
        )
        chart = bars + labels

        if show_mm:
            g["MM"] = g.groupby("Canal de Origem")["Leads"].transform(lambda s: s.rolling(mm_window, min_periods=1).mean())
            lines = alt.Chart(g).mark_line(strokeWidth=2).encode(
                x="Dia:T",
                y=alt.Y("MM:Q", title="Média móvel"),
                color=alt.Color("Canal de Origem:N", sort=ordem_c, legend=None),
            )
            chart = chart + lines

    st.altair_chart(chart.properties(height=380), use_container_width=True)

# =========================================================
# Tabelas
# =========================================================
st.markdown("### 📄 Tabelas")
with st.expander("Dados Limpos", expanded=False):
    st.dataframe(df[["Fase", "Responsável", "Nome do Negócio", "Fonte", "Criado", "Motivo de perda"]])
with st.expander("Funil Comercial do Período", expanded=False):
    st.dataframe(funil_df)
with st.expander("Taxas de Conversão por Canal", expanded=False):
    st.dataframe(conv_df)
with st.expander("Resumo por Vendedora", expanded=False):
    st.dataframe(prospec_resumo_df)
with st.expander("Funil Detalhado por Vendedora (base filtrada)", expanded=False):
    st.dataframe(prospec_funil_df)
with st.expander("Resumo por Vendedora × Origem", expanded=False):
    st.dataframe(vend_origem_df)

# =========================================================
# Exportar Excel
# =========================================================
buffer_xlsx = BytesIO()
with pd.ExcelWriter(buffer_xlsx, engine="xlsxwriter") as writer:
    df[["Fase", "Responsável", "Nome do Negócio", "Fonte", "Criado", "Motivo de perda"]].to_excel(
        writer, sheet_name="Dados_Limpos", index=False
    )
    funil_df.to_excel(writer, sheet_name="Funil_Comercial", index=False)
    conv_df.to_excel(writer, sheet_name="Conversao_Canal", index=False)
    prospec_resumo_df.to_excel(writer, sheet_name="Vendedora_Resumo", index=False)
    prospec_funil_df.to_excel(writer, sheet_name="Vendedora_Funil", index=False)
    vend_origem_df.to_excel(writer, sheet_name="Vendedora_Origem", index=False)

st.download_button(
    "⬇️ Baixar Excel",
    data=buffer_xlsx.getvalue(),
    file_name=f"Relatorio_CRM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# =========================================================
# Exportar PDF
# =========================================================
pdf_bytes = BytesIO()
with PdfPages(pdf_bytes) as pdf:
    # Capa
    fig = plt.figure(figsize=(10, 6))
    plt.axis("off")
    periodo_txt = f"{d_ini.strftime('%d/%m/%Y')} a {d_fim.strftime('%d/%m/%Y')}"
    resumo = (
        f"Período: {periodo_txt}\n"
        f"Leads: {len(df)} | Reuniões: {int(count_set(df['_fase_norm'], labels_reuniao_all))} | "
        f"Vendas: {int(count_set(df['_fase_norm'], labels_venda))}"
    )
    plt.text(0.05, 0.75, "Relatório CRM", fontsize=24, weight="bold")
    plt.text(0.05, 0.6, resumo, fontsize=14)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

    # Leads por canal
    base_plot = funil_df[funil_df["Canal de Origem"] != "TOTAL"][["Canal de Origem", "Leads Recebidos"]]
    fig = plt.figure(figsize=(10, 6))
    plt.barh(base_plot["Canal de Origem"], base_plot["Leads Recebidos"])
    plt.xlabel("Leads")
    plt.title("Leads por Canal")
    plt.tight_layout()
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

    # Conversões por canal
    fig = plt.figure(figsize=(10, 6))
    conv_plot = conv_df[conv_df["Canal de Origem"] != "TOTAL"].set_index("Canal de Origem")
    conv_plot[["% Reuniões/Leads", "% Vendas/Leads", "% Vendas/Reuniões"]].plot(kind="barh", ax=plt.gca())
    plt.xlabel("%")
    plt.title("Conversões por Canal")
    plt.tight_layout()
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

    # Resumo vendedora
    fig = plt.figure(figsize=(10, 6))
    pv = prospec_resumo_df[prospec_resumo_df["Vendedora"] != "TOTAL"].set_index("Vendedora")
    pv[["Leads Gerados", "Reuniões Agendadas", "Vendas"]].plot(kind="barh", ax=plt.gca())
    plt.title("Leads/Reuniões/Vendas por Vendedora (base filtrada)")
    plt.tight_layout()
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

    # Funil vendedora (tabela -> barras simples)
    if not prospec_funil_df.empty:
        fig = plt.figure(figsize=(11, 6))
        fases_plot_pdf = [
            "Sem retorno","Sem Interesse","Fora do Perfil","Outros/Perdido","Abaixo de R$500K",
            "Agendando Reunião","Reuniões Agendadas","Proposta e Negociação","Negócio Fechado","Em Atendimento"
        ]
        pf_plot = prospec_funil_df[prospec_funil_df["Vendedora"] != "TOTAL"].set_index("Vendedora")[fases_plot_pdf]
        pf_plot.plot(kind="bar", stacked=False, ax=plt.gca())
        plt.xticks(rotation=45, ha="right")
        plt.title("Funil por Vendedora (base filtrada)")
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

st.download_button(
    "⬇️ Baixar PDF",
    data=pdf_bytes.getvalue(),
    file_name=f"Relatorio_CRM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
    mime="application/pdf",
)
