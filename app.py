#!/usr/bin/env python3
"""Dashboard Interativo CNPJ Analytics (Streamlit + Plotly + DuckDB).

Monitoramento de Mobilidade de Porte, Setores CNAE, Distribuição Regional
e Transições de MEI entre 2023 e 2026 a partir dos microdados da Receita Federal.
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

# Configuração da página do Streamlit
st.set_page_config(
    page_title="CNPJ Analytics | Inteligência Empresarial",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilização CSS personalizada (moderno, profissional e responsivo)
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #475569;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.2rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        text-align: center;
    }
    .metric-val {
        font-size: 1.8rem;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 0.2rem;
    }
    .metric-label {
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
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


@st.cache_data
def carregar_dados_resumo() -> dict[str, pd.DataFrame]:
    """Carrega os datasets pré-processados da pasta output/."""
    arquivos = {
        "fluxo_porte": OUTPUT_DIR / "fluxo_porte.csv",
        "resumo_geral": OUTPUT_DIR / "resumo_geral.csv",
        "cnae_evol_taxa": OUTPUT_DIR / "cnae_evolucao_taxa_top10.csv",
        "cnae_evol_vol": OUTPUT_DIR / "cnae_evolucao_volume_top10.csv",
        "cnae_regr_taxa": OUTPUT_DIR / "cnae_regressao_taxa_top10.csv",
        "cnae_regr_vol": OUTPUT_DIR / "cnae_regressao_volume_top10.csv",
        "uf_evol": OUTPUT_DIR / "uf_evolucao_top5.csv",
        "uf_regr": OUTPUT_DIR / "uf_regressao_top5.csv",
        "mun_evol": OUTPUT_DIR / "municipio_evolucao_top10.csv",
        "mun_regr": OUTPUT_DIR / "municipio_regressao_top10.csv",
        "cohort_idade": OUTPUT_DIR / "cohort_idade.csv",
        "ano_concentracao": OUTPUT_DIR / "ano_concentracao.csv",
        "transicao_mei": BASE_DIR / "transicao_mei.csv",
    }
    dfs = {}
    for chave, caminho in arquivos.items():
        if caminho.exists():
            dfs[chave] = pd.read_csv(caminho)
        else:
            dfs[chave] = pd.DataFrame()
    return dfs


dados = carregar_dados_resumo()

# Barra lateral informativa e de controle
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/combo-chart.png", width=64)
    st.title("CNPJ Analytics")
    st.caption("Inteligência em Mobilidade Empresarial")
    st.divider()

    st.markdown("### 📌 Sobre a Base")
    st.markdown("""
    - **Origem:** Dados Abertos RFB
    - **Período:** 2023 (`2023-12`) vs 2026 (`2026-06`)
    - **Motor:** DuckDB (OLAP colunar)
    - **Empresas Comparáveis:** **55.911.128**
    """)
    st.divider()
    
    st.markdown("### 🏷️ Legenda de Porte (RFB)")
    st.markdown("""
    - **01:** Não Informado / Demais (Médio & Grande)
    - **03:** Microempresa (Até R$ 360k/ano)
    - **05:** EPP (R$ 360k a R$ 4,8M/ano)
    """)

# Cabeçalho Executivo
st.markdown('<div class="main-title">📊 Painel Estratégico de Dinâmica Empresarial</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Acompanhamento da transição de porte, expansão setorial, descentralização regional e migração de MEI no Brasil</div>', unsafe_allow_html=True)

# Linha de KPIs de Alto Impacto
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

total_empresas = 55911128
total_evol = 167075
total_regr = 22561
razao = total_evol / total_regr
total_mei_trans = 5445579

with kpi1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Empresas Comparáveis</div>
        <div class="metric-val">{total_empresas:,.0f}</div>
        <div style="color: #64748b; font-size: 0.8rem;">Base 2023 & 2026</div>
    </div>
    """.replace(",", "."), unsafe_allow_html=True)

with kpi2:
    st.markdown(f"""
    <div class="metric-card" style="border-top: 4px solid #10b981;">
        <div class="metric-label" style="color: #059669;">Evoluções de Porte</div>
        <div class="metric-val" style="color: #059669;">+{total_evol:,.0f}</div>
        <div style="color: #059669; font-size: 0.8rem; font-weight: 600;">0,30% da base ativa</div>
    </div>
    """.replace(",", "."), unsafe_allow_html=True)

with kpi3:
    st.markdown(f"""
    <div class="metric-card" style="border-top: 4px solid #ef4444;">
        <div class="metric-label" style="color: #dc2626;">Regressões de Porte</div>
        <div class="metric-val" style="color: #dc2626;">-{total_regr:,.0f}</div>
        <div style="color: #dc2626; font-size: 0.8rem; font-weight: 600;">0,04% da base ativa</div>
    </div>
    """.replace(",", "."), unsafe_allow_html=True)

with kpi4:
    st.markdown(f"""
    <div class="metric-card" style="border-top: 4px solid #3b82f6;">
        <div class="metric-label" style="color: #2563eb;">Taxa de Dinamismo</div>
        <div class="metric-val" style="color: #2563eb;">{razao:.2f}x</div>
        <div style="color: #2563eb; font-size: 0.8rem; font-weight: 600;">Evoluções por Regressão</div>
    </div>
    """, unsafe_allow_html=True)

with kpi5:
    st.markdown(f"""
    <div class="metric-card" style="border-top: 4px solid #8b5cf6;">
        <div class="metric-label" style="color: #7c3aed;">Migrações de MEI</div>
        <div class="metric-val" style="color: #7c3aed;">{total_mei_trans:,.0f}</div>
        <div style="color: #7c3aed; font-size: 0.8rem; font-weight: 600;">Deixaram MEI em 2026</div>
    </div>
    """.replace(",", "."), unsafe_allow_html=True)

st.write("")

# Abas Analíticas
tab_fluxo, tab_setor, tab_regiao, tab_tempo, tab_mei, tab_sql = st.tabs([
    "📈 Fluxo de Porte (Sankey)",
    "🏭 Perfil Setorial (CNAEs)",
    "🗺️ Perfil Regional (UFs & Municípios)",
    "⏳ Ciclo de Vida & Maturidade",
    "🎯 Transição de MEI",
    "⚡ Consulta SQL Interativa",
])

# -------------------------------------------------------------
# ABA 1: FLUXO DE PORTE
# -------------------------------------------------------------
with tab_fluxo:
    st.subheader("Matriz de Transição e Fluxo de Mobilidade")
    st.markdown("Compara o enquadramento de porte das empresas de 2023 para 2026.")

    col_fl1, col_fl2 = st.columns([3, 2])

    with col_fl1:
        # Diagrama de Fluxo Sankey Interativo com Plotly
        df_fl = dados["fluxo_porte"]
        if not df_fl.empty:
            df_sankey = df_fl[df_fl["categoria_transicao"].isin(["Evolução", "Regressão"])].copy()
            
            porte_nome = {
                "01": "01 (Demais / Não Inf.)",
                "03": "03 (Microempresa)",
                "05": "05 (EPP)",
            }
            
            fontes = ["2023: " + porte_nome.get(str(p), str(p)) for p in df_sankey["porte_2023"]]
            alvos = ["2026: " + porte_nome.get(str(p), str(p)) for p in df_sankey["porte_2026"]]
            
            todos_nos = sorted(list(set(fontes + alvos)))
            mapa_nos = {nome: i for i, nome in enumerate(todos_nos)}
            
            source_indices = [mapa_nos[f] for f in fontes]
            target_indices = [mapa_nos[a] for a in alvos]
            valores = df_sankey["total_empresas"].tolist()
            
            cores_links = [
                "rgba(16, 185, 129, 0.45)" if cat == "Evolução" else "rgba(239, 68, 68, 0.45)"
                for cat in df_sankey["categoria_transicao"]
            ]
            
            fig_sankey = go.Figure(data=[go.Sankey(
                node=dict(
                    pad=18,
                    thickness=22,
                    line=dict(color="#1e293b", width=0.5),
                    label=todos_nos,
                    color="#1e3a8a",
                ),
                link=dict(
                    source=source_indices,
                    target=target_indices,
                    value=valores,
                    color=cores_links,
                ),
            )])
            fig_sankey.update_layout(
                title_text="Diagrama de Sankey: Fluxo de Transição entre Portes (Evoluções em Verde, Regressões em Vermelho)",
                font_size=12,
                height=420,
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig_sankey, use_container_width=True)

    with col_fl2:
        df_fl_mud = df_fl[df_fl["categoria_transicao"].isin(["Evolução", "Regressão"])].copy()
        df_fl_mud["Par de Transição"] = df_fl_mud["porte_2023"].astype(str) + " ➔ " + df_fl_mud["porte_2026"].astype(str)
        df_fl_mud = df_fl_mud.sort_values(by="total_empresas", ascending=True)

        fig_bar_fl = px.bar(
            df_fl_mud,
            x="total_empresas",
            y="Par de Transição",
            color="categoria_transicao",
            orientation="h",
            color_discrete_map={"Evolução": "#10b981", "Regressão": "#ef4444"},
            text="total_empresas",
            title="Volume Absoluto por Transição",
        )
        fig_bar_fl.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
        fig_bar_fl.update_layout(
            height=420,
            xaxis_title="Número de Empresas",
            yaxis_title="",
            legend_title="Tipo",
            margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig_bar_fl, use_container_width=True)

    st.markdown("#### Detalhamento da Matriz de Transição Completa")
    st.dataframe(
        df_fl.style.format({
            "total_empresas": "{:,.0f}",
            "percentual_geral": "{:.4f}%",
        }),
        use_container_width=True,
    )

# -------------------------------------------------------------
# ABA 2: PERFIL SETORIAL (CNAEs)
# -------------------------------------------------------------
with tab_setor:
    st.subheader("Atividades Econômicas de Maior Mobilidade (CNAE Principal)")
    
    col_c1, col_c2 = st.columns(2)

    with col_c1:
        st.markdown("##### 🚀 Top 10 Setores com Maior Taxa de Evolução (%)")
        st.caption("Filtro de relevância estatística: mínimo de 1.000 empresas ativas no setor")
        df_c_ev = dados["cnae_evol_taxa"]
        if not df_c_ev.empty:
            df_c_ev_plot = df_c_ev.sort_values(by="taxa_evolucao_pct", ascending=True).copy()
            df_c_ev_plot["descricao_curta"] = df_c_ev_plot["nome_cnae"].str[:35] + "..."
            
            fig_c_ev = px.bar(
                df_c_ev_plot,
                x="taxa_evolucao_pct",
                y="descricao_curta",
                orientation="h",
                text="taxa_evolucao_pct",
                color_discrete_sequence=["#10b981"],
                hover_data=["cnae_fiscal_principal", "volume_evolucao", "total_empresas_cnae"],
            )
            fig_c_ev.update_traces(texttemplate="%{text:.2f}%", textposition="outside")
            fig_c_ev.update_layout(height=450, xaxis_title="Taxa de Evolução (%)", yaxis_title="")
            st.plotly_chart(fig_c_ev, use_container_width=True)

    with col_c2:
        st.markdown("##### 📉 Top 10 Setores com Maior Taxa de Regressão (%)")
        st.caption("Filtro de relevância estatística: mínimo de 1.000 empresas ativas no setor")
        df_c_rg = dados["cnae_regr_taxa"]
        if not df_c_rg.empty:
            df_c_rg_plot = df_c_rg.sort_values(by="taxa_regressao_pct", ascending=True).copy()
            df_c_rg_plot["descricao_curta"] = df_c_rg_plot["nome_cnae"].str[:35] + "..."
            
            fig_c_rg = px.bar(
                df_c_rg_plot,
                x="taxa_regressao_pct",
                y="descricao_curta",
                orientation="h",
                text="taxa_regressao_pct",
                color_discrete_sequence=["#ef4444"],
                hover_data=["cnae_fiscal_principal", "volume_regressao", "total_empresas_cnae"],
            )
            fig_c_rg.update_traces(texttemplate="%{text:.2f}%", textposition="outside")
            fig_c_rg.update_layout(height=450, xaxis_title="Taxa de Regressão (%)", yaxis_title="")
            st.plotly_chart(fig_c_rg, use_container_width=True)

    st.divider()
    st.markdown("##### 📦 Top Setores por Volume Absoluto de Evolução")
    st.dataframe(
        dados["cnae_evol_vol"].style.format({
            "volume_evolucao": "{:,.0f}",
            "total_empresas_cnae": "{:,.0f}",
            "taxa_evolucao_pct": "{:.2f}%",
        }),
        use_container_width=True,
    )

# -------------------------------------------------------------
# ABA 3: PERFIL REGIONAL
# -------------------------------------------------------------
with tab_regiao:
    st.subheader("Descentralização Geográfica do Crescimento")
    
    col_r1, col_r2 = st.columns(2)

    with col_r1:
        st.markdown("##### 🏙️ Top 5 Estados (UFs) em Volume de Evolução")
        df_uf = dados["uf_evol"]
        if not df_uf.empty:
            fig_uf = px.bar(
                df_uf.sort_values(by="volume_evolucao", ascending=True),
                x="volume_evolucao",
                y="uf",
                orientation="h",
                text="volume_evolucao",
                color="taxa_evolucao_pct",
                color_continuous_scale="Blues",
                title="Evolução por UF (com Taxa Relativa de Crescimento)",
            )
            fig_uf.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
            fig_uf.update_layout(height=380, xaxis_title="Total de Empresas", yaxis_title="UF")
            st.plotly_chart(fig_uf, use_container_width=True)

    with col_r2:
        st.markdown("##### 📍 Top 10 Municípios em Volume de Evolução")
        df_mun = dados["mun_evol"]
        if not df_mun.empty:
            df_mun_plot = df_mun.sort_values(by="volume_evolucao", ascending=True).copy()
            df_mun_plot["municipio_uf"] = df_mun_plot["nome_municipio"] + " (" + df_mun_plot["uf"] + ")"
            
            fig_mun = px.bar(
                df_mun_plot,
                x="volume_evolucao",
                y="municipio_uf",
                orientation="h",
                text="volume_evolucao",
                color_discrete_sequence=["#3b82f6"],
                title="Top Municípios Brasileiros",
            )
            fig_mun.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
            fig_mun.update_layout(height=380, xaxis_title="Total de Empresas", yaxis_title="")
            st.plotly_chart(fig_mun, use_container_width=True)

# -------------------------------------------------------------
# ABA 4: CICLO DE VIDA E MATURIDADE
# -------------------------------------------------------------
with tab_tempo:
    st.subheader("Idade da Empresa e Janela Ótima de Crescimento")
    st.markdown("Identifica como a idade da empresa (calculada via `data_inicio_atividade`) influencia a mobilidade de porte.")

    col_t1, col_t2 = st.columns([3, 2])

    with col_t1:
        df_ano = dados["ano_concentracao"]
        if not df_ano.empty:
            fig_tempo = px.line(
                df_ano,
                x="ano_abertura",
                y=["Evolução", "Regressão"],
                markers=True,
                color_discrete_map={"Evolução": "#10b981", "Regressão": "#ef4444"},
                title="Concentração de Transições por Ano de Abertura da Empresa (2000 a 2023)",
            )
            fig_tempo.update_layout(
                xaxis_title="Ano de Fundação",
                yaxis_title="Total de Transições",
                height=400,
                legend_title="Categoria",
            )
            st.plotly_chart(fig_tempo, use_container_width=True)

    with col_t2:
        df_coh = dados["cohort_idade"]
        if not df_coh.empty:
            st.markdown("##### Dinamismo por Faixa Etária")
            st.dataframe(
                df_coh.style.format({
                    "Evolução": "{:,.0f}",
                    "Regressão": "{:,.0f}",
                    "total_transicoes": "{:,.0f}",
                    "razao_evol_regr": "{:.2f}x",
                }),
                use_container_width=True,
            )
            st.info("""
            **Destaque:** Empresas na faixa de **4 a 7 anos de atividade** concentram o maior volume de ascensão econômica (quase 60 mil transições) e a maior razão positiva (**14,4x mais evoluções que regressões**).
            """)

# -------------------------------------------------------------
# ABA 5: TRANSIÇÃO MEI
# -------------------------------------------------------------
with tab_mei:
    st.subheader("Migração de Empresas MEI (2023 ➔ 2026)")
    st.markdown("Análise das empresas que eram optantes pelo MEI em 2023 e deixaram o enquadramento em 2026.")

    df_mei = dados["transicao_mei"]
    if not df_mei.empty:
        col_m1, col_m2 = st.columns([1, 1])
        
        porte_map = {
            1: "01 - Demais / Não Informado",
            3: "03 - Microempresa (ME)",
            5: "05 - Empresa de Pequeno Porte (EPP)",
            "01": "01 - Demais / Não Informado",
            "03": "03 - Microempresa (ME)",
            "05": "05 - Empresa de Pequeno Porte (EPP)",
        }
        df_mei_display = df_mei.copy()
        df_mei_display["Descrição do Porte"] = df_mei_display["novo_porte"].map(porte_map).fillna("Outro")
        
        with col_m1:
            fig_mei = px.pie(
                df_mei_display,
                values="total_empresas_que_migrararam",
                names="Descrição do Porte",
                title="Distribuição do Novo Porte pós-MEI",
                hole=0.45,
                color_discrete_sequence=["#3b82f6", "#10b981", "#8b5cf6"],
            )
            fig_mei.update_layout(height=380)
            st.plotly_chart(fig_mei, use_container_width=True)

        with col_m2:
            st.write("")
            st.write("")
            st.dataframe(
                df_mei_display[["novo_porte", "Descrição do Porte", "total_empresas_que_migrararam"]].style.format({
                    "total_empresas_que_migrararam": "{:,.0f}",
                }),
                use_container_width=True,
            )
            st.success(f"**Total que migrou:** {df_mei['total_empresas_que_migrararam'].sum():,.0f} empresas deixaram o enquadramento MEI entre 2023 e 2026.".replace(",", "."))

# -------------------------------------------------------------
# ABA 6: CONSULTA SQL INTERATIVA
# -------------------------------------------------------------
with tab_sql:
    st.subheader("⚡ Explorador SQL Direto no DuckDB")
    st.markdown("Execute consultas analíticas interativas diretamente sobre o arquivo `cnpj_comparativo.duckdb`.")

    query_padrao = """-- Amostra de empresas com transição recente
SELECT 
    e.cnpj_basico,
    e.razao_social,
    e.porte_empresa,
    e.ano_referencia
FROM empresas e
WHERE e.ano_referencia = 2026
LIMIT 10;"""

    query_usuario = st.text_area("Digite sua consulta SQL:", value=query_padrao, height=140)

    if st.button("Executar Consulta 🚀", type="primary"):
        if DB_PATH.exists():
            try:
                con = duckdb.connect(str(DB_PATH), read_only=True)
                df_query = con.execute(query_usuario).df()
                con.close()
                st.success(f"Consulta executada com sucesso! ({len(df_query)} linhas retornadas)")
                st.dataframe(df_query, use_container_width=True)
            except Exception as e:
                st.error(f"Erro na execução da consulta: {e}")
        else:
            st.error("Arquivo de banco `cnpj_comparativo.duckdb` não encontrado.")
