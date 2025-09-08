# app.py — Relatório CRM — v10 (com novas fases)
# Ajustes solicitados:
# - "Em Proposta" = ("Proposta e Negociação" + "Follow up Proposta")
# - Nova etapa "Finalizando Venda" (verde) entre "Proposta e Negociação" e "Negócio Fechado"
# - Big Numbers: Leads | Reuniões | Em Proposta | Finalizando Venda | Vendas

import streamlit as st
import pandas as pd
import unicodedata
import altair as alt
from io import BytesIO
from datetime import datetime, date
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

st.set_page_config(page_title="Relatório CRM — v10", layout="wide")
st.title("Gerador de Relatório CRM — v10")
st.caption("Envie o CSV do CRM (separador ';' ou ','). O app detecta separador e encoding automaticamente.")

# ========================= Helpers =========================
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def norm_phase(s):
    if pd.isna(s):
        return ""
    s = str(s).strip().lower()
    s = strip_accents(s)
    s = (s.replace("r$", "")
           .replace("  ", " ").replace("–", "-").replace("—", "-")
           .replace(" -", "").replace("-", " "))
    return " ".join(s.split())

def norm_text(x):
    return strip_accents(str(x).strip().lower()) if pd.notna(x) else ""

def pct(a, b):
    return round((a / b * 100) if b else 0, 2)

def count_set(series_norm, allowed_set):
    return series_norm.isin(allowed_set).sum()
    
def full_dates(start, end):
    """Retorna DataFrame com todas as datas entre start e end como coluna 'Dia' (datetime)."""
    rng = pd.date_range(pd.to_datetime(start), pd.to_datetime(end), freq="D")
    return pd.DataFrame({"Dia": pd.to_datetime(rng)})

def read_crm_csv(uploaded_file) -> pd.DataFrame:
    raw = uploaded_file.getvalue()
    enc_used = "utf-8"
    for enc in ("utf-8", "latin1"):
        try:
            _ = raw.decode(enc, errors="strict")
            enc_used = enc
            break
        except Exception:
            continue
    text = raw.decode(enc_used, errors="ignore")
    sample = "\n".join(text.splitlines()[:20])
    delim = ";" if sample.count(";") >= sample.count(",") else ","
    return pd.read_csv(
        BytesIO(raw), sep=delim, engine="python", encoding=enc_used,
        on_bad_lines="skip", dtype_backend="numpy_nullable",
    )

# ======= Filtro com Checkboxes — melhor UX =======
def checkbox_grid(label, options, key, default_all=True, columns=2):
    st.sidebar.markdown(f"**{label}**")
    if key not in st.session_state:
        st.session_state[key] = set(options if default_all else [])
    b1, b2, b3 = st.sidebar.columns(3)
    if b1.button("Todos", key=f"all_{key}"):
        st.session_state[key] = set(options)
    if b2.button("Limpar", key=f"clr_{key}"):
        st.session_state[key] = set()
    if b3.button("Inverter", key=f"inv_{key}"):
        st.session_state[key] = set([o for o in options if o not in st.session_state[key]])

    cols = st.sidebar.columns(columns)
    for i, opt in enumerate(options):
        with cols[i % columns]:
            checked = opt in st.session_state[key]
            new_val = st.checkbox(opt, value=checked, key=f"cb_{key}_{i}")
            if new_val:
                st.session_state[key].add(opt)
            else:
                st.session_state[key].discard(opt)
    return list(st.session_state[key])

# ========================= Upload =========================
up = st.file_uploader("CSV do CRM", type=["csv"])
if up is None:
    st.info("⬆️ Envie um CSV para começar.")
    st.stop()

try:
    df_raw = read_crm_csv(up)
except Exception as e:
    st.error(f"Não consegui ler o CSV. Detalhe: {e}")
    st.stop()

expected = {
    "Fase": ["Fase"],
    "Responsável": ["Responsável", "Responsavel"],
    "Nome do Negócio": ["Nome do Negócio", "Nome do negocio", "Nome do negócio"],
    "Fonte": ["Fonte"],
    "Criado": ["Criado", "Data de criação", "Data de criacao"],
    "Motivo de perda": ["Motivo de perda.1", "Motivo de perda_1", "Motivo de perda 1"],
}
colmap = {}
for wanted, cands in expected.items():
    for c in cands:
        if c in df_raw.columns:
            colmap[wanted] = c
            break
missing = [k for k in expected if k not in colmap]
if missing:
    st.error(f"Faltam colunas no CSV: {missing}\nColunas recebidas: {list(df_raw.columns)}")
    st.stop()

df = df_raw[[colmap[k] for k in expected]].copy()
df.columns = list(expected.keys())
df["Criado"] = pd.to_datetime(df["Criado"], errors="coerce", dayfirst=True)
df["_fase_norm"] = df["Fase"].apply(norm_phase)

# ===== Mapeamento de Fonte -> Canal (inclui Base CLT/SEC) =====
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
    "Google Ads","Trafego Pago - Face","Trafego Pago - Insta",
    "Impulsionamento Instagram","Prospecção Ativa","Inbound",
    "Indicação","Base CLT/SEC","Outros"
]

# ========================= Filtros =========================
st.sidebar.header("Filtros")

min_d = pd.to_datetime(df["Criado"].min()).date() if df["Criado"].notna().any() else date.today()
max_d = pd.to_datetime(df["Criado"].max()).date() if df["Criado"].notna().any() else date.today()
d_ini, d_fim = st.sidebar.date_input("Período (Criado)", value=(min_d, max_d))
if isinstance(d_ini, tuple):
    d_ini, d_fim = d_ini

vendedoras = sorted(df["Responsável"].dropna().unique().tolist())
sel_vendedoras = checkbox_grid("Vendedoras", vendedoras, key="vend_grid", default_all=True, columns=1)

canais = [c for c in canal_ordem if c in df["Canal de Origem"].unique()] + sorted(
    [c for c in df["Canal de Origem"].unique() if c not in canal_ordem]
)
c1, c2, c3 = st.sidebar.columns(3)
if c1.button("Somente Mkt"):
    st.session_state["canal_grid"] = set([c for c in canais if c in ["Google Ads","Trafego Pago - Face","Trafego Pago - Insta","Impulsionamento Instagram","Inbound"]])
if c2.button("Somente Prospecção"):
    st.session_state["canal_grid"] = set(["Prospecção Ativa"])
if c3.button("Exceto Outros"):
    st.session_state["canal_grid"] = set([c for c in canais if c != "Outros"])

sel_canais = checkbox_grid("Canais de Origem", canais, key="canal_grid", default_all=True, columns=1)

only_prospec = st.sidebar.checkbox("Focar apenas em Prospecção Ativa (gráficos por vendedora)", value=False)

mask = pd.Series(True, index=df.index)
if df["Criado"].notna().any():
    mask &= df["Criado"].dt.date.between(d_ini, d_fim)
if sel_vendedoras:
    mask &= df["Responsável"].isin(sel_vendedoras)
if sel_canais:
    mask &= df["Canal de Origem"].isin(sel_canais)
df = df[mask].copy()
base_vendedora_df = df if not only_prospec else df[df["Canal de Origem"] == "Prospecção Ativa"]

# ===== Labels / conjuntos de fases =====
# Tudo em minúsculo/sem acento, pois norm_phase normaliza
label_perdidos = {
    "Sem retorno": {"sem retorno"},
    "Sem Interesse": {"sem interesse"},
    "Fora do Perfil": {"fora do perfil"},
    "Outros/Perdido": {"outros / perdido","outros/perdido","outros perdido"},
    "Abaixo de R$500K": {"abaixo de 500k","abaixo de r$500k","abaixo de 500 k","abaixo de 500 mil"},
}
# Reuniões
labels_reuniao_agendando = {"agendando reuniao","agendamento de reuniao"}
labels_reuniao_agendada  = {"reuniao agendada","reunioes agendadas"}
labels_reuniao_all = labels_reuniao_agendando | labels_reuniao_agendada
# Proposta (AJUSTE: incluir "Follow up Proposta")
labels_proposta = {"proposta e negociacao", "follow up proposta"}
# NOVA ETAPA: Finalizando Venda (todas essas fases contam aqui)
labels_finalizando = {
    "aprovacao da proposta",
    "proposta aceita | gerar contrato",
    "compliance",
    "compliance | aguardando scd",
    "compliance | cliente em ajuste",
    "compliance aprovado",
    "clicksign | assinatura",
    "assinatura pendente",
    "enviar boleto",
    "aguardando pagamento",
    "pagamento recebido",
}
# Vendas (fechados)
labels_venda = {"negocio fechado","negocios fechados"}

# ========================= Tabelas por canal =========================
funil_rows = []
for canal in canal_ordem:
    g = df[df["Canal de Origem"] == canal]
    total = len(g)
    row = {"Canal de Origem": canal, "Leads Recebidos": total}
    for colname, variants in label_perdidos.items():
        row[colname] = count_set(g["_fase_norm"], variants)
    row["Agendando Reunião"]     = count_set(g["_fase_norm"], labels_reuniao_agendando)
    row["Reuniões Agendadas"]    = count_set(g["_fase_norm"], labels_reunio_agendada)
    row["Proposta e Negociação"] = count_set(g["_fase_norm"], labels_proposta)     # já soma Follow up
    row["Finalizando Venda"]     = count_set(g["_fase_norm"], labels_finalizando)  # NOVO
    row["Negócio Fechado"]       = count_set(g["_fase_norm"], labels_venda)
    anteriores = sum(v for k, v in row.items() if k not in {"Canal de Origem","Leads Recebidos"})
    row["Em Atendimento"]        = max(total - anteriores, 0)
    funil_rows.append(row)
funil_df = pd.DataFrame(funil_rows)
expected_cols = [
    "Canal de Origem","Leads Recebidos",
    "Sem retorno","Sem Interesse","Fora do Perfil","Outros/Perdido","Abaixo de R$500K",
    "Agendando Reunião","Reuniões Agendadas",
    "Proposta e Negociação","Finalizando Venda","Negócio Fechado",
    "Em Atendimento"
]
for c in expected_cols:
    if c not in funil_df.columns: funil_df[c] = 0
funil_df = funil_df[expected_cols]
total_row = {"Canal de Origem":"TOTAL"}
for c in expected_cols[1:]:
    total_row[c] = funil_df[c].sum()
funil_df = pd.concat([funil_df, pd.DataFrame([total_row])], ignore_index=True)

conv_rows = []
for canal in canal_ordem:
    g = df[df["Canal de Origem"] == canal]
    leads = len(g); reun = count_set(g["_fase_norm"], labels_reuniao_all); vend = count_set(g["_fase_norm"], labels_venda)
    conv_rows.append({"Canal de Origem": canal,
                      "% Reuniões/Leads": pct(reun, leads),
                      "% Vendas/Leads": pct(vend, leads),
                      "% Vendas/Reuniões": pct(vend, reun)})
leads_tot = len(df); reun_tot = count_set(df["_fase_norm"], labels_reuniao_all); vend_tot = count_set(df["_fase_norm"], labels_venda)
conv_rows.append({"Canal de Origem":"TOTAL",
                  "% Reuniões/Leads": pct(reun_tot, leads_tot),
                  "% Vendas/Leads": pct(vend_tot, leads_tot),
                  "% Vendas/Reuniões": pct(vend_tot, reun_tot)})
conv_df = pd.DataFrame(conv_rows)

# ========================= Por vendedora (respeita filtros) =========================
todas_vendedoras = sorted(base_vendedora_df["Responsável"].dropna().unique().tolist())

prospec = base_vendedora_df
prospec_rows = []
for resp in todas_vendedoras:
    g = prospec[prospec["Responsável"] == resp]
    leads = len(g); reun = count_set(g["_fase_norm"], labels_reuniao_all); vend = count_set(g["_fase_norm"], labels_venda)
    prospec_rows.append({"Vendedora": resp, "Leads Gerados": leads, "Reuniões Agendadas": reun, "Vendas": vend,
                         "Conversão Reunião (%)": pct(reun, leads), "Conversão Venda (%)": pct(vend, leads)})
prospec_rows.append({"Vendedora":"TOTAL","Leads Gerados":len(prospec),
                     "Reuniões Agendadas":count_set(prospec["_fase_norm"], labels_reuniao_all),
                     "Vendas":count_set(prospec["_fase_norm"], labels_venda),
                     "Conversão Reunião (%)": pct(count_set(prospec["_fase_norm"], labels_reuniao_all), len(prospec)) if len(prospec) else 0,
                     "Conversão Venda (%)": pct(count_set(prospec["_fase_norm"], labels_venda), len(prospec)) if len(prospec) else 0})
prospec_resumo_df = pd.DataFrame(prospec_rows)

prospec_funil_rows = []
for resp in todas_vendedoras:
    g = base_vendedora_df[base_vendedora_df["Responsável"] == resp]
    row = {"Vendedora": resp, "Leads Gerados (base filtrada)": len(g)}
    row["Sem retorno"]            = count_set(g["_fase_norm"], {"sem retorno"})
    row["Sem Interesse"]          = count_set(g["_fase_norm"], {"sem interesse"})
    row["Fora do Perfil"]         = count_set(g["_fase_norm"], {"fora do perfil"})
    row["Outros/Perdido"]         = count_set(g["_fase_norm"], {"outros / perdido","outros/perdido","outros perdido"})
    row["Abaixo de R$500K"]       = count_set(g["_fase_norm"], {"abaixo de 500k","abaixo de r$500k","abaixo de 500 k","abaixo de 500 mil"})
    row["Agendando Reunião"]      = count_set(g["_fase_norm"], {"agendando reuniao","agendamento de reuniao"})
    row["Reuniões Agendadas"]     = count_set(g["_fase_norm"], {"reuniao agendada","reunioes agendadas"})
    row["Proposta e Negociação"]  = count_set(g["_fase_norm"], labels_proposta)      # inclui Follow up
    row["Finalizando Venda"]      = count_set(g["_fase_norm"], labels_finalizando)   # NOVO
    row["Negócio Fechado"]        = count_set(g["_fase_norm"], {"negocio fechado","negocios fechados"})
    anteriores = sum(row[k] for k in [
        "Sem retorno","Sem Interesse","Fora do Perfil","Outros/Perdido","Abaixo de R$500K",
        "Agendando Reunião","Reuniões Agendadas","Proposta e Negociação","Finalizando Venda","Negócio Fechado"
    ])
    row["Em Atendimento"] = max(row["Leads Gerados (base filtrada)"] - anteriores, 0)
    prospec_funil_rows.append(row)
prospec_funil_df = pd.DataFrame(prospec_funil_rows)
if not prospec_funil_df.empty:
    tot = {"Vendedora":"TOTAL"}
    for c in prospec_funil_df.columns:
        if c!="Vendedora": tot[c]=prospec_funil_df[c].sum()
    prospec_funil_df = pd.concat([prospec_funil_df, pd.DataFrame([tot])], ignore_index=True)

vend_origem_rows = []
for resp in sorted(df["Responsável"].dropna().unique()):
    g = df[df["Responsável"] == resp]
    for origem, m in {
        "Prospecção Ativa": g["Canal de Origem"].eq("Prospecção Ativa"),
        "Leads de Mkt": g["Canal de Origem"].isin(["Google Ads","Trafego Pago - Face","Trafego Pago - Insta","Impulsionamento Instagram","Inbound"]),
    }.items():
        sub = g[m]; leads=len(sub); reun=count_set(sub["_fase_norm"], labels_reuniao_all); vend=count_set(sub["_fase_norm"], labels_venda)
        vend_origem_rows.append({"Vendedora":resp,"Origem do Lead":origem,"Leads Trabalhados":leads,
                                 "Reuniões Agendadas":reun,"Vendas":vend,
                                 "Conversão Reunião (%)":pct(reun, leads),"Conversão Venda (%)":pct(vend, leads)})
vend_origem_df = pd.DataFrame(vend_origem_rows)

# ========================= Visão geral =========================
st.markdown("### 📊 Visão Geral (após filtros)")
m1, m2, m3, m4, m5 = st.columns(5)
total_leads = len(df)
total_reunioes = int(count_set(df["_fase_norm"], labels_reuniao_all))
total_em_proposta = int(count_set(df["_fase_norm"], labels_proposta))        # Proposta + Follow up Proposta
total_finalizando = int(count_set(df["_fase_norm"], labels_finalizando))     # Nova etapa
total_vendas = int(count_set(df["_fase_norm"], labels_venda))
with m1: st.metric("Leads (Total)", total_leads)
with m2: st.metric("Reuniões (Total)", total_reunioes)
with m3: st.metric("Em Proposta (Total)", total_em_proposta)
with m4: st.metric("Finalizando Venda (Total)", total_finalizando)
with m5: st.metric("Vendas (Total)", total_vendas)

# Paleta e ordem fixa das fases (com "Finalizando Venda")
phase_order = [
    "Em Atendimento",
    "Agendando Reunião",
    "Reuniões Agendadas",
    "Proposta e Negociação",
    "Finalizando Venda",    # nova
    "Negócio Fechado",
    "Abaixo de R$500K",
    "Fora do Perfil",
    "Sem Interesse",
    "Sem retorno",
    "Outros/Perdido"
]
phase_colors = [
    "#fbbf24",  # Em Atendimento (amarelo)
    "#86efac",  # Agendando Reunião (verde claro)
    "#4ade80",  # Reuniões Agendadas (verde)
    "#22c55e",  # Proposta e Negociação (verde forte)
    "#10b981",  # Finalizando Venda (verde esmeralda)
    "#16a34a",  # Negócio Fechado (verde escuro)
    "#fca5a5",  # Abaixo de R$500K
    "#f87171",  # Fora do Perfil
    "#dc2626",  # Sem Interesse
    "#991b1b",  # Sem retorno
    "#ef4444",  # Outros/Perdido
]
phase_rank = {n:i for i,n in enumerate(phase_order)}

# Leads por canal
st.markdown("### 📈 Canais — Leads por Canal")
base = funil_df[funil_df["Canal de Origem"]!="TOTAL"][["Canal de Origem","Leads Recebidos"]]
st.altair_chart(
    alt.Chart(base).mark_bar().encode(
        x="Leads Recebidos:Q", y=alt.Y("Canal de Origem:N", sort="-x")),
    use_container_width=True
)

# Fases x Canal (normalizado, tooltip=Qtd)
# Usar a ordem global phase_order para montar a lista de fases presentes no funil_df
fases_cols = [c for c in phase_order if c in funil_df.columns and c not in ["Em Atendimento"]] + ["Em Atendimento"]
melt = funil_df[funil_df["Canal de Origem"]!="TOTAL"].melt(
    id_vars=["Canal de Origem"], value_vars=fases_cols, var_name="Fase", value_name="Qtd")
melt["fase_ord"] = melt["Fase"].map(phase_rank).astype("int64")
st.markdown("### 📊 Distribuição de Fases por Canal (proporção)")
st.altair_chart(
    alt.Chart(melt).mark_bar().encode(
        x=alt.X("sum(Qtd):Q", stack="normalize", title="Proporção"),
        y=alt.Y("Canal de Origem:N", sort="-x"),
        color=alt.Color("Fase:N", sort=phase_order, scale=alt.Scale(domain=phase_order, range=phase_colors)),
        tooltip=[alt.Tooltip("Canal de Origem:N"), alt.Tooltip("Fase:N"), alt.Tooltip("sum(Qtd):Q", title="Quantidade")],
        order=alt.Order("fase_ord:Q", sort="ascending"),
    ).properties(height=340),
    use_container_width=True
)

# Conversões por canal
conv_melt = conv_df[conv_df["Canal de Origem"]!="TOTAL"].melt(
    id_vars=["Canal de Origem"], var_name="Métrica", value_name="Valor")
st.markdown("### 📈 Conversões por Canal")
st.altair_chart(
    alt.Chart(conv_melt).mark_bar().encode(
        x=alt.X("Valor:Q", title="%"),
        y=alt.Y("Canal de Origem:N", sort="-x"),
        color="Métrica:N",
        tooltip=[alt.Tooltip("Canal de Origem:N"),alt.Tooltip("Métrica:N"),alt.Tooltip("Valor:Q", title="%")],
    ).properties(height=280),
    use_container_width=True
)

# Vendedoras (respeita filtros)
st.markdown("### 👤 Vendedoras (respeita filtros de canal)")
# mantém Leads/Reuniões/Vendas como antes
base_v = prospec_resumo_df[prospec_resumo_df["Vendedora"]!="TOTAL"][["Vendedora","Leads Gerados","Reuniões Agendadas","Vendas"]]
st.altair_chart(
    alt.Chart(base_v).transform_fold(
        ["Leads Gerados","Reuniões Agendadas","Vendas"], as_=["Métrica","Valor"]
    ).mark_bar().encode(
        x="Valor:Q", y=alt.Y("Vendedora:N", sort="-x"), color="Métrica:N",
        tooltip=[alt.Tooltip("Vendedora:N"), alt.Tooltip("Métrica:N"), alt.Tooltip("Valor:Q")]
    ).properties(height=300),
    use_container_width=True
)

# Funil detalhado por vendedora (quantidade)
st.markdown("### 📊 Funil detalhado por Vendedora")
if not prospec_funil_df.empty:
    pf = prospec_funil_df[prospec_funil_df["Vendedora"]!="TOTAL"].copy()
    fases_plot = phase_order  # já na ordem desejada (inclui Finalizando Venda)
    for c in fases_plot:
        if c not in pf.columns: pf[c]=0
    melted_v = pf.melt(id_vars=["Vendedora"], value_vars=fases_plot, var_name="Fase", value_name="Qtd")
    melted_v["fase_ord"] = melted_v["Fase"].map(phase_rank).astype("int64")
    st.altair_chart(
        alt.Chart(melted_v).mark_bar().encode(
            x=alt.X("sum(Qtd):Q", stack="zero", title="Quantidade"),
            y=alt.Y("Vendedora:N", sort="-x"),
            color=alt.Color("Fase:N", sort=phase_order, scale=alt.Scale(domain=phase_order, range=phase_colors)),
            tooltip=[alt.Tooltip("Vendedora:N"), alt.Tooltip("Fase:N"), alt.Tooltip("sum(Qtd):Q", title="Quantidade")],
            order=alt.Order("fase_ord:Q", sort="ascending")
        ).properties(height=320),
        use_container_width=True
    )

# ========================= Leads criados por dia — com dias zerados =========================
st.markdown("### 📅 Leads criados por dia")
detalhe = st.radio("Detalhar por", ["Total", "Vendedora", "Canal de Origem"], horizontal=True, key="detalhe_diario")
show_mm = st.checkbox("Mostrar média móvel", value=True, key="mm_toggle")
mm_window = st.slider("Janela da média móvel (dias)", 1, 14, 7, key="mm_diario", disabled=not show_mm)

base_daily = df[df["Criado"].notna()].copy()
if base_daily.empty:
    st.info("Nenhum lead com data de criação válida no intervalo/seleção atual.")
else:
    base_daily["Dia"] = base_daily["Criado"].dt.floor("D")
    # DataFrame com TODAS as datas do intervalo de filtros
    all_days = full_dates(d_ini, d_fim)

    if detalhe == "Total":
        g = base_daily.groupby("Dia").size().rename("Leads").reset_index()
        # left-join com TODAS as datas e preencher zeros
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
            x=alt.X("yearmonthdate(Dia):O"),
            y="Leads:Q",
            text="Leads:Q",
            color=alt.value("#ffffff"),
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
        # categorias (já filtradas pelos checkboxes)
        cats = sorted(base_daily["Responsável"].dropna().unique().tolist())
        if not cats:
            st.info("Nenhuma vendedora com dados no período/seleção atual.")
            st.stop()

        # cartesian product: todas as datas x todas as vendedoras
        grid = all_days.assign(key=1)
        cats_df = pd.DataFrame({"Responsável": cats}).assign(key=1)
        cart = grid.merge(cats_df, on="key").drop(columns="key")

        g = base_daily.groupby(["Dia", "Responsável"]).size().rename("Leads").reset_index()
        # preencher datas ausentes com zero
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

    else:  # Canal de Origem
        cats = sorted(base_daily["Canal de Origem"].dropna().unique().tolist())
        if not cats:
            st.info("Nenhum canal com dados no período/seleção atual.")
            st.stop()

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

# ========================= Tabelas =========================
st.markdown("### 📄 Tabelas")
with st.expander("Dados Limpos", expanded=False):
    st.dataframe(df[["Fase","Responsável","Nome do Negócio","Fonte","Criado","Motivo de perda"]])
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

# ========================= Exportar Excel =========================
buffer_xlsx = BytesIO()
with pd.ExcelWriter(buffer_xlsx, engine="xlsxwriter") as writer:
    df[["Fase","Responsável","Nome do Negócio","Fonte","Criado","Motivo de perda"]].to_excel(writer, "Dados_Limpos", index=False)
    funil_df.to_excel(writer, "Funil_Comercial", index=False)
    conv_df.to_excel(writer, "Conversao_Canal", index=False)
    prospec_resumo_df.to_excel(writer, "Vendedora_Resumo", index=False)
    prospec_funil_df.to_excel(writer, "Vendedora_Funil", index=False)
    vend_origem_df.to_excel(writer, "Vendedora_Origem", index=False)

st.download_button("⬇️ Baixar Excel", buffer_xlsx.getvalue(),
                   file_name=f"Relatorio_CRM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ========================= Exportar PDF =========================
pdf_bytes = BytesIO()
with PdfPages(pdf_bytes) as pdf:
    fig = plt.figure(figsize=(10,6)); plt.axis("off")
    periodo_txt = f"{d_ini.strftime('%d/%m/%Y')} a {d_fim.strftime('%d/%m/%Y')}"
    resumo = (
        f"Período: {periodo_txt}\n"
        f"Leads: {total_leads} | "
        f"Reuniões: {total_reunioes} | "
        f"Em Proposta: {total_em_proposta} | "
        f"Finalizando Venda: {total_finalizando} | "
        f"Vendas: {total_vendas}"
    )
    plt.text(0.05, 0.75, "Relatório CRM", fontsize=24, weight="bold")
    plt.text(0.05, 0.6, resumo, fontsize=14)
    pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)

    base_plot = funil_df[funil_df["Canal de Origem"]!="TOTAL"][["Canal de Origem","Leads Recebidos"]]
    fig = plt.figure(figsize=(10,6))
    plt.barh(base_plot["Canal de Origem"], base_plot["Leads Recebidos"])
    plt.xlabel("Leads"); plt.title("Leads por Canal"); plt.tight_layout()
    pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)

    fig = plt.figure(figsize=(10,6))
    conv_plot = conv_df[conv_df["Canal de Origem"]!="TOTAL"].set_index("Canal de Origem")
    conv_plot[["% Reuniões/Leads","% Vendas/Leads","% Vendas/Reuniões"]].plot(kind="barh", ax=plt.gca())
    plt.xlabel("%"); plt.title("Conversões por Canal"); plt.tight_layout()
    pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)

    fig = plt.figure(figsize=(10,6))
    pv = prospec_resumo_df[prospec_resumo_df["Vendedora"]!="TOTAL"].set_index("Vendedora")
    pv[["Leads Gerados","Reuniões Agendadas","Vendas"]].plot(kind="barh", ax=plt.gca())
    plt.title("Leads/Reuniões/Vendas por Vendedora (base filtrada)"); plt.tight_layout()
    pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)

    if not prospec_funil_df.empty:
        fig = plt.figure(figsize=(11,6))
        pf_plot = prospec_funil_df[prospec_funil_df["Vendedora"]!="TOTAL"].set_index("Vendedora")[phase_order]
        pf_plot.plot(kind="bar", stacked=False, ax=plt.gca())
        plt.xticks(rotation=45, ha="right"); plt.title("Funil por Vendedora (base filtrada)"); plt.tight_layout()
        pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)

st.download_button("⬇️ Baixar PDF", pdf_bytes.getvalue(),
                   file_name=f"Relatorio_CRM_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                   mime="application/pdf")
