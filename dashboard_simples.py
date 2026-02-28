import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import ast
import os

st.set_page_config(
    page_title="Painel STF – Controle Concentrado",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

COLORS = {
    "ADI": "#2563eb",
    "ADPF": "#dc2626",
    "ADC": "#16a34a",
    "ADO": "#d97706",
}

UF_NAMES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo",
    "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia",
    "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe",
    "TO": "Tocantins",
}

PETITIONER_CATEGORIES = {
    "PGR": ["PROCURADOR-GERAL DA REPÚBLICA"],
    "Partidos Políticos": ["PARTIDO", "DIRETÓRIO NACIONAL", "COMISSÃO EXECUTIVA NACIONAL"],
    "Governadores": ["GOVERNADOR"],
    "OAB": ["ORDEM DOS ADVOGADOS"],
    "Confederações/Sindicatos": ["CONFEDERA", "SINDICATO", "FEDERAÇÃO", "FEDERACAO", "CENTRAL ÚNICA", "CENTRAL UNICA"],
    "Assembleias/Câmaras": ["ASSEMBLEIA LEGISLATIVA", "MESA DA CÂMARA", "MESA DO SENADO", "MESA DA ASSEMBLEIA"],
    "Presidente da República": ["PRESIDENTE DA REPÚBLICA", "PRESIDENTE DA REPUBLICA"],
}


def categorize_petitioner(name: str) -> str:
    upper = str(name).upper()
    for category, patterns in PETITIONER_CATEGORIES.items():
        if any(p in upper for p in patterns):
            return category
    return "Outros"


@st.cache_data(show_spinner="Carregando dados do STF...")
def load_data(path: str) -> pd.DataFrame:
    light_cols = [
        "incidente", "classe", "nome_processo", "classe_extenso",
        "tipo_processo", "liminar", "origem", "relator", "autor1",
        "len(partes_total)", "data_protocolo", "origem_orgao",
        "lista_assuntos", "len(andamentos_lista)", "len(decisões)",
        "len(deslocamentos)", "status_processo",
    ]
    df = pd.read_csv(path, usecols=light_cols)

    df["data_protocolo"] = pd.to_datetime(df["data_protocolo"], format="%d/%m/%Y", errors="coerce")
    df["ano"] = df["data_protocolo"].dt.year
    df["tem_liminar"] = df["liminar"].str.contains("MEDIDA LIMINAR", na=False)
    df["origem_valida"] = df["origem"].apply(lambda x: x if x in UF_NAMES else None)
    df["categoria_autor"] = df["autor1"].apply(categorize_petitioner)

    return df


# --- Sidebar ---
def apply_sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filtros")

    classes = st.sidebar.multiselect(
        "Classe processual",
        options=sorted(df["classe"].unique()),
        default=sorted(df["classe"].unique()),
    )
    status = st.sidebar.multiselect(
        "Status",
        options=sorted(df["status_processo"].unique()),
        default=sorted(df["status_processo"].unique()),
    )
    min_year = int(df["ano"].min()) if df["ano"].notna().any() else 1988
    max_year = int(df["ano"].max()) if df["ano"].notna().any() else 2026
    year_range = st.sidebar.slider(
        "Ano de protocolo", min_value=min_year, max_value=max_year,
        value=(min_year, max_year),
    )

    mask = (
        df["classe"].isin(classes)
        & df["status_processo"].isin(status)
        & df["ano"].between(year_range[0], year_range[1])
    )
    return df[mask]


# --- Tabs ---

def render_overview(df):
    st.header("Visão Geral")

    cols = st.columns(6)
    cols[0].metric("Total de Processos", f"{len(df):,}")
    cols[1].metric("ADI", f"{(df['classe'] == 'ADI').sum():,}")
    cols[2].metric("ADPF", f"{(df['classe'] == 'ADPF').sum():,}")
    cols[3].metric("ADC", f"{(df['classe'] == 'ADC').sum():,}")
    cols[4].metric("ADO", f"{(df['classe'] == 'ADO').sum():,}")
    pct = (df["status_processo"] == "Em andamento").mean() * 100
    cols[5].metric("Em Andamento", f"{pct:.1f}%")

    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        status_df = df["status_processo"].value_counts().reset_index()
        status_df.columns = ["Status", "Quantidade"]
        fig = px.pie(status_df, names="Status", values="Quantidade",
                     title="Status dos Processos",
                     color="Status",
                     color_discrete_map={"Finalizado": "#6b7280", "Em andamento": "#2563eb"},
                     hole=0.4)
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        classe_df = df["classe"].value_counts().reset_index()
        classe_df.columns = ["Classe", "Quantidade"]
        fig = px.bar(classe_df, x="Classe", y="Quantidade",
                     title="Processos por Classe",
                     color="Classe", color_discrete_map=COLORS, text_auto=True)
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        tipo_df = df["tipo_processo"].value_counts().reset_index()
        tipo_df.columns = ["Tipo", "Quantidade"]
        fig = px.pie(tipo_df, names="Tipo", values="Quantidade",
                     title="Tipo de Processo",
                     color="Tipo",
                     color_discrete_map={"Físico": "#9333ea", "Eletrônico": "#0891b2"},
                     hole=0.4)
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with c4:
        lim = df["tem_liminar"].value_counts().reset_index()
        lim.columns = ["Liminar", "Quantidade"]
        lim["Liminar"] = lim["Liminar"].map({True: "Com Liminar", False: "Sem Liminar"})
        fig = px.pie(lim, names="Liminar", values="Quantidade",
                     title="Medidas Liminares",
                     color="Liminar",
                     color_discrete_map={"Com Liminar": "#dc2626", "Sem Liminar": "#6b7280"},
                     hole=0.4)
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)


def render_temporal(df):
    st.header("Análise Temporal")

    yearly = df.groupby(["ano", "classe"]).size().reset_index(name="quantidade")
    yearly = yearly.dropna(subset=["ano"])
    yearly["ano"] = yearly["ano"].astype(int)

    fig = px.bar(yearly, x="ano", y="quantidade", color="classe",
                 title="Processos Protocolados por Ano",
                 color_discrete_map=COLORS,
                 labels={"ano": "Ano", "quantidade": "Processos", "classe": "Classe"})
    fig.update_layout(barmode="stack", xaxis_dtick=2)
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        cum = df.dropna(subset=["ano"]).sort_values("ano").groupby("ano").size().cumsum().reset_index(name="acumulado")
        fig = px.area(cum, x="ano", y="acumulado",
                      title="Acúmulo de Processos ao Longo do Tempo",
                      labels={"ano": "Ano", "acumulado": "Total Acumulado"})
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        tipo_year = df.dropna(subset=["ano"]).groupby(["ano", "tipo_processo"]).size().reset_index(name="quantidade")
        tipo_year["ano"] = tipo_year["ano"].astype(int)
        fig = px.area(tipo_year, x="ano", y="quantidade", color="tipo_processo",
                      title="Transição: Processos Físicos → Eletrônicos",
                      color_discrete_map={"Físico": "#9333ea", "Eletrônico": "#0891b2"},
                      labels={"ano": "Ano", "quantidade": "Processos", "tipo_processo": "Tipo"})
        st.plotly_chart(fig, use_container_width=True)


def render_geographic(df):
    st.header("Distribuição Geográfica")

    geo_df = df[df["origem_valida"].notna()].groupby("origem_valida").size().reset_index(name="quantidade")
    geo_df.columns = ["UF", "quantidade"]
    geo_df["Estado"] = geo_df["UF"].map(UF_NAMES)

    fig = px.bar(geo_df, x="quantidade", y="UF", orientation="h",
                 title="Processos por Estado de Origem",
                 color="quantidade", color_continuous_scale="Blues",
                 labels={"quantidade": "Processos", "UF": "Estado"},
                 hover_data=["Estado"])
    fig.update_layout(height=700, yaxis=dict(categoryorder="total ascending"))
    fig.update_coloraxes(showscale=False)
    st.plotly_chart(fig, use_container_width=True)


def render_justices(df):
    st.header("Relatores (Ministros)")

    rel_df = df["relator"].value_counts().reset_index()
    rel_df.columns = ["Relator", "Processos"]

    fig = px.bar(rel_df, x="Processos", y="Relator", orientation="h",
                 title="Distribuição de Processos por Relator",
                 color="Processos", color_continuous_scale="Reds")
    fig.update_layout(height=max(500, len(rel_df) * 22),
                      yaxis=dict(categoryorder="total ascending"))
    fig.update_coloraxes(showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Atividade dos Relatores ao Longo do Tempo")
    selected = st.multiselect(
        "Selecione relatores para comparar:",
        options=rel_df["Relator"].tolist(),
        default=rel_df.nlargest(5, "Processos")["Relator"].tolist(),
    )
    if selected:
        rel_time = (df[df["relator"].isin(selected)].dropna(subset=["ano"])
                    .groupby(["ano", "relator"]).size().reset_index(name="quantidade"))
        rel_time["ano"] = rel_time["ano"].astype(int)
        fig = px.line(rel_time, x="ano", y="quantidade", color="relator",
                      title="Processos Distribuídos por Ano",
                      labels={"ano": "Ano", "quantidade": "Processos", "relator": "Relator"},
                      markers=True)
        st.plotly_chart(fig, use_container_width=True)


def render_petitioners(df):
    st.header("Autores / Requerentes")

    c1, c2 = st.columns(2)
    with c1:
        cat_df = df["categoria_autor"].value_counts().reset_index()
        cat_df.columns = ["Categoria", "Processos"]
        fig = px.pie(cat_df, names="Categoria", values="Processos",
                     title="Processos por Categoria de Autor", hole=0.35)
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        top = df["autor1"].value_counts().head(15).reset_index()
        top.columns = ["Autor", "Processos"]
        fig = px.bar(top, x="Processos", y="Autor", orientation="h",
                     title="Top 15 Autores (Requerentes)",
                     color="Processos", color_continuous_scale="Oranges")
        fig.update_layout(yaxis=dict(categoryorder="total ascending"))
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)


def render_complexity(df):
    st.header("Complexidade Processual")

    c1, c2 = st.columns(2)
    with c1:
        fig = px.box(df, x="classe", y="len(andamentos_lista)", color="classe",
                     title="Andamentos por Classe",
                     color_discrete_map=COLORS,
                     labels={"classe": "Classe", "len(andamentos_lista)": "Nº de Andamentos"})
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        fig = px.box(df, x="classe", y="len(decisões)", color="classe",
                     title="Decisões por Classe",
                     color_discrete_map=COLORS,
                     labels={"classe": "Classe", "len(decisões)": "Nº de Decisões"})
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    complexity = df.groupby("classe").agg(
        andamentos_med=("len(andamentos_lista)", "median"),
        decisoes_med=("len(decisões)", "median"),
        partes_med=("len(partes_total)", "median"),
        deslocamentos_med=("len(deslocamentos)", "median"),
    ).reset_index()

    fig = go.Figure()
    for _, row in complexity.iterrows():
        fig.add_trace(go.Scatterpolar(
            r=[row["andamentos_med"], row["decisoes_med"],
               row["partes_med"], row["deslocamentos_med"]],
            theta=["Andamentos", "Decisões", "Partes", "Deslocamentos"],
            fill="toself", name=row["classe"],
            line=dict(color=COLORS.get(row["classe"])),
        ))
    fig.update_layout(title="Perfil de Complexidade por Classe (Medianas)",
                      polar=dict(radialaxis=dict(visible=True)))
    st.plotly_chart(fig, use_container_width=True)


def render_explorer(df):
    st.header("Explorar Processos")

    c1, c2 = st.columns(2)
    with c1:
        search = st.text_input("Buscar por nome do processo ou autor:", "")
    with c2:
        classe_filter = st.multiselect("Classe:", df["classe"].unique().tolist(),
                                       default=df["classe"].unique().tolist())

    filtered = df[df["classe"].isin(classe_filter)]
    if search:
        mask = (filtered["nome_processo"].str.contains(search, case=False, na=False)
                | filtered["autor1"].str.contains(search, case=False, na=False))
        filtered = filtered[mask]

    display_cols = ["nome_processo", "classe_extenso", "relator", "autor1",
                    "origem", "data_protocolo", "status_processo", "tipo_processo",
                    "len(andamentos_lista)", "len(decisões)"]
    renamed = {
        "nome_processo": "Processo", "classe_extenso": "Classe",
        "relator": "Relator", "autor1": "Autor Principal",
        "origem": "UF", "data_protocolo": "Protocolo",
        "status_processo": "Status", "tipo_processo": "Tipo",
        "len(andamentos_lista)": "Andamentos", "len(decisões)": "Decisões",
    }

    st.caption(f"Exibindo {len(filtered):,} de {len(df):,} processos")
    st.dataframe(
        filtered[display_cols].rename(columns=renamed).sort_values("Protocolo", ascending=False),
        use_container_width=True, height=600,
    )


# --- Main ---
def main():
    CSV_PATH = "ArquivosConcatenados_1.csv"

    if not os.path.exists(CSV_PATH):
        st.error(f"Arquivo `{CSV_PATH}` não encontrado. Coloque-o na raiz do projeto.")
        return

    df_raw = load_data(CSV_PATH)
    df = apply_sidebar_filters(df_raw)

    st.sidebar.divider()
    st.sidebar.caption(f"**{len(df):,}** processos selecionados de **{len(df_raw):,}**")

    st.title("⚖️ Painel STF – Controle Concentrado de Constitucionalidade")
    st.caption(
        "ADIs, ADPFs, ADCs e ADOs extraídos do portal do STF • "
        f"Dados de {int(df_raw['ano'].min())} a {int(df_raw['ano'].max())}"
    )

    tabs = st.tabs([
        "📊 Visão Geral",
        "📅 Temporal",
        "🗺️ Geográfico",
        "👤 Relatores",
        "📝 Autores",
        "📈 Complexidade",
        "🔍 Explorar",
    ])

    with tabs[0]:
        render_overview(df)
    with tabs[1]:
        render_temporal(df)
    with tabs[2]:
        render_geographic(df)
    with tabs[3]:
        render_justices(df)
    with tabs[4]:
        render_petitioners(df)
    with tabs[5]:
        render_complexity(df)
    with tabs[6]:
        render_explorer(df)


if __name__ == "__main__":
    main()
