#!/usr/bin/env python3
"""Dashboard Interativo CNPJ Analytics (Streamlit + DuckDB + Plotly).

Recursos implementados:
1. Filtro dinâmico de UFs na barra lateral (multiselect com as 27 UFs do Brasil).
2. Consultas SQL dinâmicas com cláusula WHERE uf IN (...) em todas as CTEs analíticas.
3. Visão comparativa com Barchart Agrupado (barmode='group') por UF quando múltiplas UFs forem selecionadas.
4. Cards com métricas de proporção e variação percentual de empresas ativas (2023 vs 2026) individualizados por UF.
5. Módulo analítico de Sobrevivência e Novos Entrantes.
"""
from __future__ import annotations

from pathlib import Path
import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Diretórios
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
DB_PATH = BASE_DIR / "cnpj_comparativo.duckdb"
PARQUET_TRANSICOES = OUTPUT_DIR / "transicoes_detalhadas.parquet"
CSV_METRICAS_UF = OUTPUT_DIR / "metricas_uf.csv"

# Lista oficial das 27 Unidades da Federação do Brasil
UFS_BRASIL = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
    "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
    "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]

# Configuração da página Streamlit
st.set_page_config(
    page_title="CNPJ Analytics | Inteligência Empresarial",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilização CSS Moderna
st.markdown("""
<style>
    .main-title {
        font-size: 2.1rem;
        font-weight: 800;
        color: #1e3a8a;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.0rem;
        color: #475569;
        margin-bottom: 1.2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 1.0rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        text-align: center;
        margin-bottom: 0.8rem;
    }
    .metric-val {
        font-size: 1.6rem;
        font-weight: 800;
        color: #0f172a;
    }
    .metric-label {
        font-size: 0.82rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #64748b;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
        border-radius: 8px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# =====================================================================
# FUNÇÕES DE CONSULTA SQL DINÂMICAS COM FILTRO DE UF (DUCKDB + CACHE)
# =====================================================================

def montar_filtro_uf_sql(ufs: tuple[str, ...], prefix_where: bool = True, extra_cond: str = "") -> str:
    """Gera cláusula SQL segura para filtragem de UFs com suporte a 0, 1 ou N UFs.
    
    Garante sintaxe SQL válida para DuckDB mesmo com tuplas de elemento único ('SP').
    """
    if not ufs:
        if extra_cond:
            return f"WHERE {extra_cond}" if prefix_where else f"AND {extra_cond}"
        return ""
    
    lista_formatada = ", ".join(f"'{u}'" for u in ufs)
    cond_uf = f"uf IN ({lista_formatada})"
    
    if extra_cond:
        cond_final = f"{cond_uf} AND {extra_cond}"
    else:
        cond_final = cond_uf
        
    return f"WHERE {cond_final}" if prefix_where else f"AND {cond_final}"


@st.cache_data
def carregar_lista_ufs() -> list[str]:
    """Retorna as 27 UFs oficiais do Brasil (otimizado para economizar processamento)."""
    return UFS_BRASIL


@st.cache_data
def carregar_metricas_base_uf() -> pd.DataFrame:
    """Carrega o histórico consolidado de empresas e ativas por UF (2023 vs 2026)."""
    if CSV_METRICAS_UF.exists():
        return pd.read_csv(CSV_METRICAS_UF)
    
    # Fallback caso o CSV ainda não exista: consulta direta no DuckDB
    con = duckdb.connect(str(DB_PATH), read_only=True)
    sql = """
    SELECT 
        ano_referencia, 
        uf, 
        count(*) as total_empresas,
        count(CASE WHEN situacao_cadastral = '02' THEN 1 END) as ativas
    FROM estabelecimentos 
    WHERE identificador_matriz_filial = '1'
    GROUP BY 1, 2 
    ORDER BY 2, 1;
    """
    df = con.execute(sql).df()
    con.close()
    return df


@st.cache_data
def consultar_fluxo_porte(ufs: tuple[str, ...]) -> pd.DataFrame:
    """Executa a CTE de transição de porte aceitando filtro dinâmico de UFs."""
    con = duckdb.connect()
    clausula_where = montar_filtro_uf_sql(ufs)
    
    # Consulta usando CTE SQL sobre o dataset detalhado
    sql = f"""
    WITH transicoes_filtradas AS (
        SELECT 
            uf,
            porte_2023,
            porte_2026,
            porte_2023 || ' -> ' || porte_2026 AS transicao,
            tipo_transicao
        FROM '{PARQUET_TRANSICOES.as_posix()}'
        {clausula_where}
    )
    SELECT 
        uf,
        porte_2023,
        porte_2026,
        transicao,
        tipo_transicao,
        COUNT(*) AS total_empresas
    FROM transicoes_filtradas
    GROUP BY uf, porte_2023, porte_2026, transicao, tipo_transicao
    ORDER BY total_empresas DESC;
    """
    df = con.execute(sql).df()
    con.close()
    return df


@st.cache_data
def consultar_crescimento_setorial(ufs: tuple[str, ...], top_n: int = 10) -> pd.DataFrame:
    """Consulta os setores CNAE com maior volume de evolução aceitando filtro de UFs."""
    con = duckdb.connect()
    clausula_where = montar_filtro_uf_sql(ufs)
    
    # CTEs dinâmicas com filtragem por UF
    sql = f"""
    WITH transicoes_base AS (
        SELECT 
            uf,
            cnae_fiscal_principal,
            nome_cnae,
            tipo_transicao
        FROM '{PARQUET_TRANSICOES.as_posix()}'
        {clausula_where}
    ),
    ranking_setores AS (
        SELECT 
            cnae_fiscal_principal,
            nome_cnae,
            COUNT(CASE WHEN tipo_transicao = 'Evolução' THEN 1 END) as total_evolucao_setor,
            COUNT(CASE WHEN tipo_transicao = 'Regressão' THEN 1 END) as total_regressao_setor
        FROM transicoes_base
        GROUP BY cnae_fiscal_principal, nome_cnae
        ORDER BY total_evolucao_setor DESC
        LIMIT {top_n}
    )
    SELECT 
        t.uf,
        t.cnae_fiscal_principal,
        r.nome_cnae,
        SUBSTRING(r.nome_cnae, 1, 35) || '...' AS descricao_curta,
        COUNT(CASE WHEN t.tipo_transicao = 'Evolução' THEN 1 END) as volume_evolucao,
        COUNT(CASE WHEN t.tipo_transicao = 'Regressão' THEN 1 END) as volume_regressao,
        COUNT(*) as total_transicoes
    FROM transicoes_base t
    JOIN ranking_setores r ON t.cnae_fiscal_principal = r.cnae_fiscal_principal
    GROUP BY t.uf, t.cnae_fiscal_principal, r.nome_cnae
    ORDER BY volume_evolucao DESC;
    """
    df = con.execute(sql).df()
    con.close()
    return df


@st.cache_data
def consultar_taxa_sobrevivencia_entrantes(ufs: tuple[str, ...]) -> dict[str, float | int]:
    """Calcula taxa de sobrevivência (empresas ativas em 2026) e novos entrantes via SQL com filtro de UF."""
    con = duckdb.connect()
    clausula_where = montar_filtro_uf_sql(ufs)
    
    sql = f"""
    WITH metricas_filtradas AS (
        SELECT 
            ano_referencia,
            uf,
            total_empresas,
            ativas
        FROM '{CSV_METRICAS_UF.as_posix()}'
        {clausula_where}
    )
    SELECT 
        COALESCE(SUM(CASE WHEN ano_referencia = 2023 THEN total_empresas ELSE 0 END), 0) AS total_2023,
        COALESCE(SUM(CASE WHEN ano_referencia = 2026 THEN total_empresas ELSE 0 END), 0) AS total_2026,
        COALESCE(SUM(CASE WHEN ano_referencia = 2023 THEN ativas ELSE 0 END), 0) AS ativas_2023,
        COALESCE(SUM(CASE WHEN ano_referencia = 2026 THEN ativas ELSE 0 END), 0) AS ativas_2026
    FROM metricas_filtradas;
    """
    row = con.execute(sql).fetchone()
    con.close()
    
    t23, t26, at23, at26 = row if row else (0, 0, 0, 0)
    novos_entrantes = max(0, t26 - t23)
    var_ativas_pct = ((at26 - at23) / at23 * 100) if at23 > 0 else 0.0
    taxa_atividade = (at26 / t26 * 100) if t26 > 0 else 0.0
    
    return {
        "total_2023": int(t23),
        "total_2026": int(t26),
        "ativas_2023": int(at23),
        "ativas_2026": int(at26),
        "novos_entrantes": int(novos_entrantes),
        "var_ativas_pct": float(var_ativas_pct),
        "taxa_atividade": float(taxa_atividade),
    }


@st.cache_data
def consultar_municipios(ufs: tuple[str, ...], top_n: int = 10) -> pd.DataFrame:
    """Retorna os municípios líderes em evolução dentro das UFs selecionadas via SQL."""
    con = duckdb.connect()
    clausula_where = montar_filtro_uf_sql(ufs, prefix_where=True, extra_cond="tipo_transicao = 'Evolução'")
    
    sql = f"""
    WITH evolucoes_municipio AS (
        SELECT 
            uf,
            nome_municipio,
            nome_municipio || ' (' || uf || ')' AS municipio_uf
        FROM '{PARQUET_TRANSICOES.as_posix()}'
        {clausula_where}
    )
    SELECT 
        uf,
        nome_municipio,
        municipio_uf,
        COUNT(*) AS volume_evolucao
    FROM evolucoes_municipio
    GROUP BY uf, nome_municipio, municipio_uf
    ORDER BY volume_evolucao DESC
    LIMIT {top_n};
    """
    df = con.execute(sql).df()
    con.close()
    return df


@st.cache_data
def consultar_ciclo_vida(ufs: tuple[str, ...]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retorna a concentração temporal por ano de fundação e coortes etárias via SQL."""
    con = duckdb.connect()
    clausula_where = montar_filtro_uf_sql(ufs)
    
    sql_ano = f"""
    WITH dados_limpos AS (
        SELECT 
            TRY_CAST(SUBSTRING(data_inicio_atividade, 1, 4) AS INTEGER) AS ano_abertura,
            tipo_transicao
        FROM '{PARQUET_TRANSICOES.as_posix()}'
        {clausula_where}
    )
    SELECT 
        ano_abertura,
        COUNT(CASE WHEN tipo_transicao = 'Evolução' THEN 1 END) AS Evolução,
        COUNT(CASE WHEN tipo_transicao = 'Regressão' THEN 1 END) AS Regressão
    FROM dados_limpos
    WHERE ano_abertura BETWEEN 2000 AND 2023
    GROUP BY ano_abertura
    ORDER BY ano_abertura;
    """
    df_ano = con.execute(sql_ano).df()

    sql_coorte = f"""
    WITH idades AS (
        SELECT 
            2026 - TRY_CAST(SUBSTRING(data_inicio_atividade, 1, 4) AS INTEGER) AS idade,
            tipo_transicao
        FROM '{PARQUET_TRANSICOES.as_posix()}'
        {clausula_where}
    ),
    faixas AS (
        SELECT 
            CASE 
                WHEN idade <= 3 THEN '1. Até 3 anos (Jovem / Start)'
                WHEN idade <= 7 THEN '2. 4 a 7 anos (Crescimento)'
                WHEN idade <= 15 THEN '3. 8 a 15 anos (Consolidação)'
                WHEN idade <= 25 THEN '4. 16 a 25 anos (Madura)'
                ELSE '5. Mais de 25 anos (Tradicional)'
            END AS faixa_etaria,
            tipo_transicao
        FROM idades
        WHERE idade >= 0 AND idade <= 100
    )
    SELECT 
        faixa_etaria,
        COUNT(CASE WHEN tipo_transicao = 'Evolução' THEN 1 END) AS Evolução,
        COUNT(CASE WHEN tipo_transicao = 'Regressão' THEN 1 END) AS Regressão,
        COUNT(*) AS total_transicoes,
        ROUND(CAST(COUNT(CASE WHEN tipo_transicao = 'Evolução' THEN 1 END) AS DOUBLE) / 
              NULLIF(COUNT(CASE WHEN tipo_transicao = 'Regressão' THEN 1 END), 0), 2) AS razao_evol_regr
    FROM faixas
    GROUP BY faixa_etaria
    ORDER BY faixa_etaria;
    """
    df_coorte = con.execute(sql_coorte).df()
    con.close()
    return df_ano, df_coorte


# =====================================================================
# SIDEBAR: FILTROS DINÂMICOS
# =====================================================================

st.sidebar.image("https://img.icons8.com/fluency/96/combo-chart.png", width=60)
st.sidebar.title("Filtros de Análise")

# 1. Filtro Multiselect de UF (conforme solicitado pelo usuário)
ufs_selecionadas_lista = st.sidebar.multiselect(
    "Selecione as UFs para Análise",
    options=carregar_lista_ufs(),
    default=[],
    help="Selecione uma ou mais UFs para filtrar e comparar os dados. Deixe vazio para o Panorama Nacional.",
)

# Converte em tupla para hashing seguro nas funções com @st.cache_data
ufs_filtro = tuple(sorted(ufs_selecionadas_lista))
qtd_ufs = len(ufs_filtro)

if qtd_ufs == 0:
    st.sidebar.info("🌐 **Escopo Atual:** Brasil (Panorama Nacional)")
elif qtd_ufs == 1:
    st.sidebar.success(f"📍 **Escopo Atual:** Estado de **{ufs_filtro[0]}**")
else:
    st.sidebar.success(f"⚖️ **Modo Comparativo:** {qtd_ufs} Estados selecionados ({', '.join(ufs_filtro)})")

st.sidebar.divider()
st.sidebar.markdown("### 📌 Parâmetros e Regras")
st.sidebar.markdown("""
- **Porte 01:** Não Informado / Demais
- **Porte 03:** Microempresa (ME)
- **Porte 05:** Empresa de Pequeno Porte (EPP)
""")
st.sidebar.caption("Base: Receita Federal (2023-12 vs 2026-06)")


# =====================================================================
# CABEÇALHO E MÉTRICAS DE PROPORÇÃO POR UF (CARDS NO TOPO)
# =====================================================================

st.markdown('<div class="main-title">📈 Painel de Mobilidade e Dinâmica Empresarial</div>', unsafe_allow_html=True)
if qtd_ufs == 0:
    st.markdown('<div class="sub-title">Visão Consolidada Nacional (Brasil) — Acompanhamento de porte, setores, sobrevivência e migração de MEI</div>', unsafe_allow_html=True)
else:
    st.markdown(f'<div class="sub-title">Visão Regional Comparativa para: <b>{", ".join(ufs_filtro)}</b></div>', unsafe_allow_html=True)

# Carrega métricas de empresas ativas por UF
df_metricas_todas = carregar_metricas_base_uf()

st.markdown("#### 🏢 Variação Percentual do Total de Empresas Ativas (2023 -> 2026)")

if qtd_ufs > 0:
    # Se UFs foram selecionadas, renderiza um st.metric individual para cada UF
    # Distribuídos em até 4 colunas por linha
    linhas_ufs = [ufs_filtro[i:i + 4] for i in range(0, len(ufs_filtro), 4)]
    for linha in linhas_ufs:
        colunas_cards = st.columns(len(linha))
        for col, uf in zip(colunas_cards, linha):
            sub_uf = df_metricas_todas[df_metricas_todas["uf"] == uf]
            at23 = sub_uf[sub_uf["ano_referencia"] == 2023]["ativas"].sum()
            at26 = sub_uf[sub_uf["ano_referencia"] == 2026]["ativas"].sum()
            delta_pct = ((at26 - at23) / at23 * 100) if at23 > 0 else 0.0
            
            with col:
                st.metric(
                    label=f"Ativas em {uf} (2026)",
                    value=f"{at26:,.0f}".replace(",", "."),
                    delta=f"{delta_pct:+.2f}% vs 2023",
                    help=f"Em 2023: {at23:,.0f} empresas ativas cadastradas.".replace(",", "."),
                )
else:
    # Panorama Nacional (sem UF selecionada)
    k1, k2, k3, k4 = st.columns(4)
    at23_br = df_metricas_todas[df_metricas_todas["ano_referencia"] == 2023]["ativas"].sum()
    at26_br = df_metricas_todas[df_metricas_todas["ano_referencia"] == 2026]["ativas"].sum()
    delta_br = ((at26_br - at23_br) / at23_br * 100) if at23_br > 0 else 0.0
    
    tot23_br = df_metricas_todas[df_metricas_todas["ano_referencia"] == 2023]["total_empresas"].sum()
    tot26_br = df_metricas_todas[df_metricas_todas["ano_referencia"] == 2026]["total_empresas"].sum()
    delta_tot_br = ((tot26_br - tot23_br) / tot23_br * 100) if tot23_br > 0 else 0.0

    with k1:
        st.metric(
            label="Empresas Ativas Brasil (2026)",
            value=f"{at26_br:,.0f}".replace(",", "."),
            delta=f"{delta_br:+.2f}% vs 2023",
        )
    with k2:
        st.metric(
            label="Total Cadastrado Brasil (2026)",
            value=f"{tot26_br:,.0f}".replace(",", "."),
            delta=f"{delta_tot_br:+.2f}% vs 2023",
        )
    with k3:
        st.metric(
            label="Evoluções de Porte (2023-2026)",
            value="+167.075",
            delta="+0,30% da base comparável",
        )
    with k4:
        st.metric(
            label="Regressões de Porte (2023-2026)",
            value="-22.561",
            delta="-0,04% da base comparável",
            delta_color="inverse",
        )

st.divider()

# =====================================================================
# ABAS ANALÍTICAS COM CONSULTAS DINÂMICAS
# =====================================================================

tab_fluxo, tab_setor, tab_regiao, tab_sobrevivencia, tab_ciclo = st.tabs([
    "📈 Evolução de Porte (Comparativo)",
    "🏭 Crescimento Setorial (CNAEs)",
    "🗺️ Ranking Regional (Municípios)",
    "🛡️ Sobrevivência & Novos Entrantes",
    "⏳ Ciclo de Vida & Maturidade",
])

# ---------------------------------------------------------------------
# ABA 1: EVOLUÇÃO DE PORTE (BARCHART AGRUPADO POR UF)
# ---------------------------------------------------------------------
with tab_fluxo:
    st.subheader("Mobilidade de Porte das Empresas")
    
    df_fluxo_uf = consultar_fluxo_porte(ufs_filtro)
    
    if df_fluxo_uf.empty:
        st.warning("Nenhum registro encontrado para os filtros selecionados.")
    else:
        # Agrega dados para exibição
        if qtd_ufs > 1:
            # Modo Comparativo: Barchart Agrupado por UF (barmode='group')
            st.info(f"💡 **Gráfico Comparativo Agrupado:** Comparação direta de volume de transição entre as UFs: {', '.join(ufs_filtro)}.")
            
            fig_bar_porte = px.bar(
                df_fluxo_uf,
                x="transicao",
                y="total_empresas",
                color="uf",
                barmode="group",
                text="total_empresas",
                title=f"Comparativo de Transição de Porte Agrupado por Estado ({', '.join(ufs_filtro)})",
                labels={"transicao": "Par de Transição", "total_empresas": "Número de Empresas", "uf": "Estado (UF)"},
                color_discrete_sequence=px.colors.qualitative.Bold,
            )
            fig_bar_porte.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
            fig_bar_porte.update_layout(
                height=480,
                xaxis_title="Transição de Porte (2023 -> 2026)",
                yaxis_title="Total de Empresas",
                legend_title="UF",
            )
            st.plotly_chart(fig_bar_porte, use_container_width=True)
            
        else:
            # Panorama de 1 UF ou Nacional: visualização consolidada
            col_f1, col_f2 = st.columns([3, 2])
            
            # Agrupa transições somando todas as UFs do filtro
            df_fl_agg = df_fluxo_uf.groupby(["transicao", "tipo_transicao"])["total_empresas"].sum().reset_index()
            df_fl_agg = df_fl_agg.sort_values(by="total_empresas", ascending=True)

            with col_f1:
                fig_bar_single = px.bar(
                    df_fl_agg,
                    x="total_empresas",
                    y="transicao",
                    color="tipo_transicao",
                    orientation="h",
                    text="total_empresas",
                    color_discrete_map={"Evolução": "#10b981", "Regressão": "#ef4444"},
                    title="Volume por Transição de Porte",
                    labels={"transicao": "Transição", "total_empresas": "Empresas", "tipo_transicao": "Tipo"},
                )
                fig_bar_single.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
                fig_bar_single.update_layout(height=420)
                st.plotly_chart(fig_bar_single, use_container_width=True)

            with col_f2:
                tot_ev = df_fl_agg[df_fl_agg["tipo_transicao"] == "Evolução"]["total_empresas"].sum()
                tot_rg = df_fl_agg[df_fl_agg["tipo_transicao"] == "Regressão"]["total_empresas"].sum()
                r_din = (tot_ev / tot_rg) if tot_rg > 0 else 0.0

                fig_pie = px.pie(
                    names=["Evolução de Porte", "Regressão de Porte"],
                    values=[tot_ev, tot_rg],
                    color=["Evolução de Porte", "Regressão de Porte"],
                    color_discrete_map={"Evolução de Porte": "#10b981", "Regressão de Porte": "#ef4444"},
                    hole=0.45,
                    title="Proporção Evolução vs. Regressão",
                )
                fig_pie.update_layout(height=420)
                st.plotly_chart(fig_pie, use_container_width=True)

        st.markdown("##### Dados Tabulares da Transição")
        st.dataframe(
            df_fluxo_uf.style.format({"total_empresas": "{:,.0f}"}),
            use_container_width=True,
        )

# ---------------------------------------------------------------------
# ABA 2: CRESCIMENTO SETORIAL (CNAEs)
# ---------------------------------------------------------------------
with tab_setor:
    st.subheader("Crescimento Setorial por Atividade Econômica (CNAE)")
    
    top_cnaes_n = st.slider("Quantidade de setores no ranking:", min_value=5, max_value=20, value=10)
    df_cnae_din = consultar_crescimento_setorial(ufs_filtro, top_n=top_cnaes_n)

    if df_cnae_din.empty:
        st.warning("Nenhum registro setorial encontrado para as UFs selecionadas.")
    else:
        if qtd_ufs > 1:
            # Gráfico Agrupado por UF (barmode='group')
            st.info(f"💡 **Gráfico Comparativo por Setor:** Barras agrupadas por UF permitindo comparar o volume setorial entre {', '.join(ufs_filtro)}.")
            
            fig_cnae_comp = px.bar(
                df_cnae_din,
                x="descricao_curta",
                y="volume_evolucao",
                color="uf",
                barmode="group",
                text="volume_evolucao",
                title=f"Evolução por Setor Econômico Agrupado por UF (Top {top_cnaes_n} CNAEs)",
                labels={"descricao_curta": "Setor CNAE", "volume_evolucao": "Empresas que Evoluíram", "uf": "Estado (UF)"},
                color_discrete_sequence=px.colors.qualitative.Safe,
            )
            fig_cnae_comp.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
            fig_cnae_comp.update_layout(
                height=520,
                xaxis_tickangle=-35,
                xaxis_title="",
                yaxis_title="Total de Empresas",
                legend_title="UF",
            )
            st.plotly_chart(fig_cnae_comp, use_container_width=True)
            
        else:
            # Visualização horizontal padrão
            df_cnae_single = df_cnae_din.groupby(["cnae_fiscal_principal", "nome_cnae", "descricao_curta"])["volume_evolucao"].sum().reset_index()
            df_cnae_single = df_cnae_single.sort_values(by="volume_evolucao", ascending=True)

            fig_cnae_h = px.bar(
                df_cnae_single,
                x="volume_evolucao",
                y="descricao_curta",
                orientation="h",
                text="volume_evolucao",
                color_discrete_sequence=["#2563eb"],
                title=f"Top {top_cnaes_n} Setores em Volume de Evolução de Porte",
                labels={"descricao_curta": "Setor", "volume_evolucao": "Empresas"},
                hover_data=["cnae_fiscal_principal", "nome_cnae"],
            )
            fig_cnae_h.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
            fig_cnae_h.update_layout(height=480, xaxis_title="Número de Empresas", yaxis_title="")
            st.plotly_chart(fig_cnae_h, use_container_width=True)

        st.markdown("##### Tabela Detalhada por CNAE")
        st.dataframe(
            df_cnae_din[["uf", "cnae_fiscal_principal", "nome_cnae", "volume_evolucao", "volume_regressao", "total_transicoes"]].style.format({
                "volume_evolucao": "{:,.0f}",
                "volume_regressao": "{:,.0f}",
                "total_transicoes": "{:,.0f}",
            }),
            use_container_width=True,
        )

# ---------------------------------------------------------------------
# ABA 3: RANKING REGIONAL (MUNICÍPIOS)
# ---------------------------------------------------------------------
with tab_regiao:
    st.subheader("Descentralização Municipal da Evolução de Porte")
    
    top_mun_n = st.slider("Quantidade de municípios no ranking:", min_value=5, max_value=25, value=10)
    df_mun_din = consultar_municipios(ufs_filtro, top_n=top_mun_n)

    if df_mun_din.empty:
        st.warning("Nenhum município localizado para os filtros informados.")
    else:
        fig_mun = px.bar(
            df_mun_din.sort_values(by="volume_evolucao", ascending=True),
            x="volume_evolucao",
            y="municipio_uf",
            orientation="h",
            color="uf" if qtd_ufs > 1 else None,
            text="volume_evolucao",
            color_discrete_sequence=px.colors.qualitative.Dark24,
            title=f"Top {top_mun_n} Municípios em Crescimento de Porte",
            labels={"municipio_uf": "Município", "volume_evolucao": "Empresas que Evoluíram", "uf": "UF"},
        )
        fig_mun.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
        fig_mun.update_layout(height=460, xaxis_title="Total de Empresas", yaxis_title="")
        st.plotly_chart(fig_mun, use_container_width=True)

# ---------------------------------------------------------------------
# ABA 4: SOBREVIVÊNCIA E NOVOS ENTRANTES
# ---------------------------------------------------------------------
with tab_sobrevivencia:
    st.subheader("Dinâmica Demográfica: Sobrevivência e Novos Entrantes")
    
    dados_sob = consultar_taxa_sobrevivencia_entrantes(ufs_filtro)
    
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.metric(
            label="Total Cadastrado (2026)",
            value=f"{dados_sob['total_2026']:,.0f}".replace(",", "."),
            delta=f"+{dados_sob['total_2026'] - dados_sob['total_2023']:,.0f} vs 2023".replace(",", "."),
        )
    with s2:
        st.metric(
            label="Empresas Ativas (2026)",
            value=f"{dados_sob['ativas_2026']:,.0f}".replace(",", "."),
            delta=f"{dados_sob['var_ativas_pct']:+.2f}% vs 2023",
        )
    with s3:
        st.metric(
            label="Novos Entrantes Líquidos",
            value=f"{dados_sob['novos_entrantes']:,.0f}".replace(",", "."),
            help="Crescimento líquido do acervo cadastral de matrizes entre 2023 e 2026.",
        )
    with s4:
        st.metric(
            label="Taxa de Atividade / Sobrevivência",
            value=f"{dados_sob['taxa_atividade']:.1f}%",
            help="Proporção de empresas com situação cadastral Ativa em relação ao total cadastrado.",
        )

    st.write("")
    col_gr1, col_gr2 = st.columns(2)
    
    with col_gr1:
        fig_demog = go.Figure(data=[
            go.Bar(name="Total Cadastrado", x=["2023", "2026"], y=[dados_sob["total_2023"], dados_sob["total_2026"]], marker_color="#94a3b8"),
            go.Bar(name="Empresas Ativas", x=["2023", "2026"], y=[dados_sob["ativas_2023"], dados_sob["ativas_2026"]], marker_color="#0284c7"),
        ])
        fig_demog.update_layout(
            barmode="group",
            title="Evolução do Acervo: Total de Matrizes vs. Empresas Ativas",
            height=380,
            yaxis_title="Empresas",
        )
        st.plotly_chart(fig_demog, use_container_width=True)

    with col_gr2:
        baixas_inaptas = dados_sob["total_2026"] - dados_sob["ativas_2026"]
        fig_status = px.pie(
            names=["Ativas (Situação 02)", "Baixadas / Inaptas / Suspensas"],
            values=[dados_sob["ativas_2026"], baixas_inaptas],
            hole=0.45,
            color=["Ativas (Situação 02)", "Baixadas / Inaptas / Suspensas"],
            color_discrete_map={"Ativas (Situação 02)": "#0284c7", "Baixadas / Inaptas / Suspensas": "#cbd5e1"},
            title="Composição da Situação Cadastral em 2026",
        )
        fig_status.update_layout(height=380)
        st.plotly_chart(fig_status, use_container_width=True)

# ---------------------------------------------------------------------
# ABA 5: CICLO DE VIDA E MATURIDADE
# ---------------------------------------------------------------------
with tab_ciclo:
    st.subheader("Maturidade Corporativa e Idade da Empresa")
    
    df_ano_ab, df_coorte_ab = consultar_ciclo_vida(ufs_filtro)

    col_cv1, col_cv2 = st.columns([3, 2])

    with col_cv1:
        if not df_ano_ab.empty:
            fig_lin_tempo = px.line(
                df_ano_ab,
                x="ano_abertura",
                y=["Evolução", "Regressão"],
                markers=True,
                color_discrete_map={"Evolução": "#10b981", "Regressão": "#ef4444"},
                title="Transições por Ano de Fundação da Empresa (2000 a 2023)",
            )
            fig_lin_tempo.update_layout(
                xaxis_title="Ano de Abertura",
                yaxis_title="Transições",
                height=400,
                legend_title="Tipo",
            )
            st.plotly_chart(fig_lin_tempo, use_container_width=True)

    with col_cv2:
        if not df_coorte_ab.empty:
            st.markdown("##### Mobilidade por Faixa de Idade")
            st.dataframe(
                df_coorte_ab.style.format({
                    "Evolução": "{:,.0f}",
                    "Regressão": "{:,.0f}",
                    "total_transicoes": "{:,.0f}",
                    "razao_evol_regr": "{:.2f}x",
                }),
                use_container_width=True,
            )
            st.info("""
            **Padrão Empírico:** Empresas de **4 a 7 anos de atividade** concentram a maior probabilidade de expansão e desenquadramento para patamares superiores de porte.
            """)
