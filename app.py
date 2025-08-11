# app.py — Relatório CRM (robusto) — v5

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
st.set_page_config(page_title="Relatório CRM — v5", layout="wide")
st.title("Gerador de Relatório CRM — v5 (Gráficos + Filtros + PDF)")
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

# ---------- leitor ROBUSTO do CSV ----------
def read_crm_csv(uploaded_file) -> pd.DataFrame:
    """
    - Detecta encoding (utf-8 ou latin1)
    - Detecta delimitador (; ou ,)
    - Ignora linhas quebradas (on_bad_lines='skip')
    """
    raw = uploaded_file.getvalue()

    # 1) Tenta decodificar
    enc_used = "utf-8"
    for enc in ("utf-8", "latin1"):
        try:
            _ = raw.decode(enc, errors="strict")
            enc_used = enc
            break
        except Exception:
            continue
    text = raw.decode(enc_used, errors="ignore")

    # 2) Detecta delimitador por amostragem
    sample = "\n".join(text.splitlines()[:20])
    delim = ";" if sample.count(";") >= sample.count(",") else ","

    # 3) Lê com pandas a partir de bytes
    return pd.read_csv(
        BytesIO(raw),
        sep=delim,
        engine="python",
        encoding=enc_used,
        on_bad_lines="skip",
        dtype_backend="numpy_nullable",  # mais tolerante
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
    # no CRM existem 2 "Motivo de perda"; queremos a SEGUNDA (normalmente 'Motivo de perda.1')
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
# Mapeamento "Fonte" -> "Canal de Origem"
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
    "Outros",
]

# =========================================================
# Filtros
# =========================================================
st.sidebar.header("Filtros")

min_d = pd.to_datetime(df["Criado"].min()).date() if df["Criado"].notna().any() else date.today()
max_d = pd.to_datetime(df["Criado"].max()).date() if df["Criado"].notna().any() else date.today()
d_ini, d_fim = st.sidebar.date_input("Período (Criado)", value=(min_d, max_d))
if isinstance(d_ini, tuple):
    d_ini, d_fim = d_ini

vendedoras = sorted(df["Responsável"].dropna().unique().tolist())
sel_vendedoras = st.sidebar.multiselect("Vendedoras", options=vendedoras, default=vendedoras)

canais = [c for c in canal_ordem if c in df["Canal de Origem"].unique()] + sorted(
    [c for c in df["Canal de Origem"].unique() if c not in canal_ordem]
)
sel_canais = st.sidebar.multiselect("Canais de Origem", options=canais, default=canais)

mask = pd.Series(True, index=df.index)
if df["Criado"].notna().any():
    mask &= df["Criado"].dt.date.between(d_ini, d_fim)
if sel_vendedoras:
    mask &= df["Responsável"].isin(sel_vendedoras)
if sel_canais:
    mask &= df["Canal de Origem"].isin(sel_canais)

df = df[mask].copy()

# =========================================================
# Labels / Conjuntos
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
# Tabelas
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

# 3) Prospecção Ativa — Resumo por Vendedora
todas_vendedoras = sorted(df["Responsável"].dropna().unique().tolist())
prospec = df[df["Canal de Origem"] == "Prospecção Ativa"]
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

# 4) Prospecção Ativa — Funil Detalhado por Vendedora
prospec_funil_rows = []
for resp in todas_vendedoras:
    g = prospec[prospec["Responsável"] == resp]
    row = {"Vendedora": resp, "Leads Gerados (prospecção ativa)": len(g)}
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
    row["Em Atendimento"] = max(row["Leads Gerados (prospecção ativa)"] - anteriores, 0)
    prospec_funil_rows.append(row)
prospec_funil_df = pd.DataFrame(prospec_funil_rows)
if not prospec_funil_df.empty:
    tot = {"Vendedora": "TOTAL"}
    for c in prospec_funil_df.columns:
        if c != "Vendedora":
            tot[c] = prospec_funil_df[c].sum()
    prospec_funil_df = pd.concat([prospec_funil_df, pd.DataFrame([tot])], ignore_index=True)

# 5) Resumo por Vendedora × Origem
canais_mkt = ["Google Ads", "Trafego Pago - Face", "Trafego Pago - Insta", "Impulsionamento Instagram", "Inbound"]
vend_origem_rows = []
for resp in todas_vendedoras:
    g = df[df["Responsável"] == resp]
    for origem, mask in {
        "Prospecção Ativa": g["Canal de Origem"].eq("Prospecção Ativa"),
        "Leads de Mkt": g["Canal de Origem"].isin(canais_mkt),
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

st.markdown("### 📈 Canais")
base = funil_df[funil_df["Canal de Origem"] != "TOTAL"][["Canal de Origem", "Leads Recebidos"]]
chart_leads = alt.Chart(base).mark_bar().encode(
    x="Leads Recebidos:Q", y=alt.Y("Canal de Origem:N", sort="-x")
)
st.altair_chart(chart_leads.properties(height=300), use_container_width=True)

fases_cols = [
    "Sem retorno","Sem Interesse","Fora do Perfil","Outros/Perdido","Abaixo de R$500K",
    "Agendando Reunião","Reuniões Agendadas","Proposta e Negociação","Negócio Fechado","Em Atendimento"
]
melt = funil_df[funil_df["Canal de Origem"] != "TOTAL"].melt(
    id_vars=["Canal de Origem"],
    value_vars=fases_cols,
    var_name="Fase",
    value_name="Qtd",
)
chart_stack = alt.Chart(melt).mark_bar().encode(
    x=alt.X("Qtd:Q", stack="normalize", title="Proporção"),
    y="Canal de Origem:N",
    color=alt.Color("Fase:N"),
)
st.altair_chart(chart_stack.properties(height=350), use_container_width=True)

conv_melt = conv_df[conv_df["Canal de Origem"] != "TOTAL"].melt(
    id_vars=["Canal de Origem"], var_name="Métrica", value_name="Valor"
)
chart_conv = alt.Chart(conv_melt).mark_bar().encode(
    x=alt.X("Valor:Q", title="%"),
    y=alt.Y("Canal de Origem:N", sort="-x"),
    color="Métrica:N",
)
st.altair_chart(chart_conv.properties(height=280), use_container_width=True)

st.markdown("### 👤 Vendedoras (Prospecção Ativa)")
base_v = prospec_resumo_df[prospec_resumo_df["Vendedora"] != "TOTAL"][["Vendedora", "Leads Gerados", "Reuniões Agendadas", "Vendas"]]
chart_v = alt.Chart(base_v).transform_fold(
    ["Leads Gerados", "Reuniões Agendadas", "Vendas"], as_=["Métrica", "Valor"]
).mark_bar().encode(
    x="Valor:Q",
    y=alt.Y("Vendedora:N", sort="-x"),
    color="Métrica:N",
)
st.altair_chart(chart_v.properties(height=300), use_container_width=True)

conv_v = prospec_resumo_df[prospec_resumo_df["Vendedora"] != "TOTAL"][
    ["Vendedora", "Conversão Reunião (%)", "Conversão Venda (%)"]
].melt(id_vars=["Vendedora"], var_name="Métrica", value_name="Valor")
chart_conv_v = alt.Chart(conv_v).mark_bar().encode(
    x=alt.X("Valor:Q", title="%"),
    y=alt.Y("Vendedora:N", sort="-x"),
    color="Métrica:N",
)
st.altair_chart(chart_conv_v.properties(height=250), use_container_width=True)

st.markdown("### 📊 Funil Detalhado por Vendedora — Gráfico (Agrupado)")
if not prospec_funil_df.empty:
    pf_plot = prospec_funil_df[prospec_funil_df["Vendedora"] != "TOTAL"].copy()
    fases_plot = [
        "Sem retorno","Sem Interesse","Fora do Perfil","Outros/Perdido","Abaixo de R$500K",
        "Agendando Reunião","Reuniões Agendadas","Proposta e Negociação","Negócio Fechado","Em Atendimento"
    ]
    melted = pf_plot.melt(id_vars=["Vendedora"], value_vars=fases_plot, var_name="Fase", value_name="Qtd")
    chart_pf = alt.Chart(melted).mark_bar().encode(
        x="Vendedora:N",
        y="Qtd:Q",
        color="Fase:N",
    )
    st.altair_chart(chart_pf.properties(height=320), use_container_width=True)

# =========================================================
# Tabelas
# =========================================================
st.markdown("### 📄 Tabelas")
with st.expander("Dados Limpos", expanded=False):
    st.dataframe(df[["Fase", "Responsável", "Nome do Negócio", "Fonte", "Criado", "Motivo de perda"]])
with st.expander("Funil Comercial do Período", expanded=True):
    st.dataframe(funil_df)
with st.expander("Taxas de Conversão por Canal", expanded=False):
    st.dataframe(conv_df)
with st.expander("Prospecção Ativa - Resumo por Vendedora", expanded=False):
    st.dataframe(prospec_resumo_df)
with st.expander("Funil Detalhado por Vendedora (Prospecção Ativa)", expanded=False):
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
    prospec_resumo_df.to_excel(writer, sheet_name="Prospec_Resumo", index=False)
    prospec_funil_df.to_excel(writer, sheet_name="Prospec_Funil", index=False)
    vend_origem_df.to_excel(writer, sheet_name="Vendedora_Origem", index=False)

st.download_button(
    "⬇️ Baixar Excel",
    data=buffer_xlsx.getvalue(),
    file_name=f"Relatorio_CRM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# =========================================================
# Exportar PDF (matplotlib)
# =========================================================
pdf_bytes = BytesIO()
with PdfPages(pdf_bytes) as pdf:
    # 0) Capa / Sumário
    fig = plt.figure(figsize=(10, 6))
    plt.axis("off")
    periodo_txt = f"{d_ini.strftime('%d/%m/%Y')} a {d_fim.strftime('%d/%m/%Y')}"
    resumo = (
        f"Período: {perido_txt}\n"
        f"Leads: {len(df)} | Reuniões: {int(count_set(df['_fase_norm'], labels_reuniao_all))} | "
        f"Vendas: {int(count_set(df['_fase_norm'], labels_venda))}"
    )
    plt.text(0.05, 0.75, "Relatório CRM", fontsize=24, weight="bold")
    plt.text(0.05, 0.6, resumo, fontsize=14)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

    # 1) Leads por canal
    base_plot = funil_df[funil_df["Canal de Origem"] != "TOTAL"][["Canal de Origem", "Leads Recebidos"]]
    fig = plt.figure(figsize=(10, 6))
    plt.barh(base_plot["Canal de Origem"], base_plot["Leads Recebidos"])
    plt.xlabel("Leads")
    plt.title("Leads por Canal")
    plt.tight_layout()
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

    # 2) Conversões por canal
    fig = plt.figure(figsize=(10, 6))
    conv_plot = conv_df[conv_df["Canal de Origem"] != "TOTAL"].set_index("Canal de Origem")
    conv_plot[["% Reuniões/Leads", "% Vendas/Leads", "% Vendas/Reuniões"]].plot(kind="barh", ax=plt.gca())
    plt.xlabel("%")
    plt.title("Conversões por Canal")
    plt.tight_layout()
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

    # 3) Prospecção ativa por vendedora
    fig = plt.figure(figsize=(10, 6))
    pv = prospec_resumo_df[prospec_resumo_df["Vendedora"] != "TOTAL"].set_index("Vendedora")
    pv[["Leads Gerados", "Reuniões Agendadas", "Vendas"]].plot(kind="barh", ax=plt.gca())
    plt.title("Prospecção Ativa — Leads/Reuniões/Vendas por Vendedora")
    plt.tight_layout()
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

    # 4) Funil detalhado por vendedora (agrupado)
    if not prospec_funil_df.empty:
        fig = plt.figure(figsize=(11, 6))
        fases_plot = [
            "Sem retorno","Sem Interesse","Fora do Perfil","Outros/Perdido","Abaixo de R$500K",
            "Agendando Reunião","Reuniões Agendadas","Proposta e Negociação","Negócio Fechado","Em Atendimento"
        ]
        pf_plot = prospec_funil_df[prospec_funil_df["Vendedora"] != "TOTAL"].set_index("Vendedora")[fases_plot]
        pf_plot.plot(kind="bar", stacked=False, ax=plt.gca())
        plt.xticks(rotation=45, ha="right")
        plt.title("Funil Detalhado por Vendedora (Prospecção Ativa)")
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

st.download_button(
    "⬇️ Baixar PDF",
    data=pdf_bytes.getvalue(),
    file_name=f"Relatorio_CRM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
    mime="application/pdf",
)


