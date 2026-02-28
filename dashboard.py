import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import ast
import json
import re
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
    "Partidos Políticos": [
        "PARTIDO", "DIRETÓRIO NACIONAL", "COMISSÃO EXECUTIVA NACIONAL",
    ],
    "Governadores": ["GOVERNADOR"],
    "OAB": ["ORDEM DOS ADVOGADOS"],
    "Confederações/Sindicatos": [
        "CONFEDERA", "SINDICATO", "FEDERAÇÃO", "FEDERACAO",
        "CENTRAL ÚNICA", "CENTRAL UNICA",
    ],
    "Assembleias/Câmaras": [
        "ASSEMBLEIA LEGISLATIVA", "MESA DA CÂMARA", "MESA DO SENADO",
        "MESA DA ASSEMBLEIA",
    ],
    "Presidente da República": ["PRESIDENTE DA REPÚBLICA", "PRESIDENTE DA REPUBLICA"],
}


def categorize_petitioner(name: str) -> str:
    upper = str(name).upper()
    for category, patterns in PETITIONER_CATEGORIES.items():
        if any(p in upper for p in patterns):
            return category
    return "Outros"


_MONO_GRANT = {
    "LIMINAR POR DESPACHO - DEFERIDA",
    "DECISÃO LIMINAR - DEFERIDA",
    "DECISÃO DA PRESIDÊNCIA - LIMINAR DEFERIDA",
    "LIMINAR JULGADA PELO PRESIDENTE - DEFERIDA",
    "Liminar deferida",
    "Liminar deferida ad referendum",
}
_MONO_GRANT_PART = {
    "LIMINAR POR DESPACHO - DEFERIDA EM PARTE",
    "DECISÃO DA PRESIDÊNCIA - LIMINAR DEFERIDA EM PARTE",
    "Liminar deferida em parte",
    "Liminar parcialmente deferida ad referendum",
}
_MONO_DENY = {
    "LIMINAR POR DESPACHO - INDEFERIDA",
    "LIMINAR POR DESPACHO - NAO CONHECIDA",
    "LIMINAR POR DESPACHO - NEGADO SEGUIMENTO",
    "DECISÃO LIMINAR - INDEFERIDA",
    "DECISÃO DA PRESIDÊNCIA - LIMINAR INDEFERIDA",
    "LIMINAR JULGADA PELO PRESIDENTE - INDEFERIDA",
    "Liminar indeferida",
    "Liminar indeferida ad referendum",
}
_MONO_ALL_GRANT = _MONO_GRANT | _MONO_GRANT_PART

_COL_GRANT = {
    "LIMINAR JULGADA PELO PLENO - DEFERIDA",
    "LIMINAR REFERENDADO PELO PLENO",
    "LIMINAR JULG. PELO PLENO - REFERENDO",
    "LIMINAR REFERENDADO EM PARTE PELO PLENO",
    "Liminar referendada",
    "Liminar referendada em parte",
    "Decisão Referendada",
}
_COL_GRANT_PART = {
    "LIMINAR JULG. PLENO - DEFERIDA EM PARTE",
    "LIMINAR REFERENDADO EM PARTE PELO PLENO",
    "Liminar referendada em parte",
}
_COL_DENY = {
    "LIMINAR JULGADA PELO PLENO - INDEFERIDA",
    "LIMINAR JULG. PLENO - NAO CONHECIDA",
    "LIMINAR JULGADA PELO PLENO - PREJUDICADA",
    "LIMINAR NÃO REFERENDADO PELO PLENO",
    "Liminar não referendada",
}
_COL_ALL = _COL_GRANT | _COL_DENY


_ALL_LIMINAR = (
    _MONO_GRANT | _MONO_GRANT_PART | _MONO_DENY
    | _COL_GRANT | _COL_GRANT_PART | _COL_DENY
)


def _classify_liminar(
    andamentos_json: str, liminar_flag: str,
) -> tuple[str, str, int]:
    """Returns (tipo_liminar, resultado_liminar, n_decisoes_liminar).

    n_decisoes_liminar counts every individual liminar-related andamento,
    so a case with a monocratic grant + collegial referendo = 2.
    """
    try:
        andamentos = json.loads(andamentos_json)
    except Exception:
        return ("Sem decisão liminar", "", 0)

    nomes = [a.get("nome", "") for a in andamentos]
    n_dec = sum(1 for n in nomes if n in _ALL_LIMINAR)

    has_mono_grant = any(n in _MONO_ALL_GRANT for n in nomes)
    has_mono_deny = any(n in _MONO_DENY for n in nomes)
    has_col_grant = any(n in _COL_GRANT for n in nomes)
    has_col_deny = any(n in _COL_DENY for n in nomes)
    has_collegial = has_col_grant or has_col_deny

    has_tpi = any(
        a.get("nome") == "Requerida Tutela Provisória Incidental"
        or "Tutela Provisória Incidental" in a.get("complemento", "")
        for a in andamentos
    )

    if has_mono_grant and has_col_grant:
        return ("MC-Ref (mono → referendada)", "Deferida", n_dec)
    if has_mono_grant and has_col_deny:
        return ("MC-Ref (mono → referendada)", "Não referendada", n_dec)

    if has_collegial and not has_mono_grant:
        if has_col_grant:
            part = any(n in _COL_GRANT_PART for n in nomes)
            return ("MC (colegiada)", "Deferida em parte" if part else "Deferida", n_dec)
        return ("MC (colegiada)", "Indeferida", n_dec)

    if has_mono_grant and not has_collegial:
        part = any(n in _MONO_GRANT_PART for n in nomes)
        tipo = "TPI (monocrática)" if has_tpi else "Monocrática (sem referendo)"
        return (tipo, "Deferida em parte" if part else "Deferida", n_dec)

    if has_mono_deny and not has_collegial:
        tipo = "TPI (monocrática)" if has_tpi else "Monocrática (sem referendo)"
        return (tipo, "Indeferida", n_dec)

    return ("Sem decisão liminar", "", 0)


@st.cache_data(show_spinner="Carregando dados do STF...")
def load_data(path: str) -> pd.DataFrame:
    light_cols = [
        "incidente", "classe", "nome_processo", "classe_extenso",
        "tipo_processo", "liminar", "origem", "relator", "autor1",
        "len(partes_total)", "data_protocolo", "origem_orgao",
        "lista_assuntos", "len(andamentos_lista)", "len(decisões)",
        "len(deslocamentos)", "status_processo",
    ]
    df = pd.read_csv(path, usecols=light_cols + ["andamentos_lista"])

    df["data_protocolo"] = pd.to_datetime(
        df["data_protocolo"], format="%d/%m/%Y", errors="coerce"
    )
    df["ano"] = df["data_protocolo"].dt.year
    df["decada"] = (df["ano"] // 10 * 10).astype("Int64")

    df["tem_liminar"] = df["liminar"].str.contains(
        "MEDIDA LIMINAR", na=False
    )

    liminar_class = df.apply(
        lambda r: _classify_liminar(r["andamentos_lista"], r["liminar"]),
        axis=1,
    )
    df["tipo_liminar"] = liminar_class.apply(lambda x: x[0])
    df["resultado_liminar"] = liminar_class.apply(lambda x: x[1])
    df["n_decisoes_liminar"] = liminar_class.apply(lambda x: x[2])
    df.drop(columns=["andamentos_lista"], inplace=True)

    df["origem_valida"] = df["origem"].apply(
        lambda x: x if x in UF_NAMES else None
    )

    df["categoria_autor"] = df["autor1"].apply(categorize_petitioner)

    df["assuntos_parsed"] = df["lista_assuntos"].apply(safe_parse_list)

    return df


def safe_parse_list(val):
    try:
        return ast.literal_eval(val)
    except Exception:
        return []


_RE_DATE_RANGE = re.compile(
    r"Agendado para:\s*(\d{2}/\d{2}/\d{4})\s*a\s*(\d{2}/\d{2}/\d{4})"
)
_RE_DATE_SINGLE = re.compile(r"Agendado para:\s*(\d{2}/\d{2}/\d{4})")
_RE_LISTA = re.compile(r"Lista\s+([\w\-\.]+)")

MONTHS_PT = {
    "Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4,
    "Maio": 5, "Junho": 6, "Julho": 7, "Agosto": 8,
    "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12,
}
_RE_FIM_VIRTUAL = re.compile(
    r"Finalizado.*?(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})"
)


def _parse_date(s: str):
    try:
        return pd.to_datetime(s, format="%d/%m/%Y")
    except Exception:
        return pd.NaT


@st.cache_data(show_spinner="Extraindo sessões virtuais dos andamentos...")
def load_virtual_sessions(path: str) -> pd.DataFrame:
    raw = pd.read_csv(
        path,
        usecols=["nome_processo", "classe", "relator", "andamentos_lista"],
    )

    records = []
    for _, row in raw.iterrows():
        try:
            andamentos = json.loads(row["andamentos_lista"])
        except Exception:
            continue

        iniciados = {}
        finalizados = {}
        inclusoes = {}

        for a in andamentos:
            nome = a.get("nome", "")
            comp = a.get("complemento", "")
            data = a.get("data", "")

            if nome == "Iniciado Julgamento Virtual":
                iniciados[data] = a

            elif nome == "Finalizado Julgamento Virtual":
                m = _RE_FIM_VIRTUAL.search(comp)
                if m:
                    day, month_pt, year = m.group(1), m.group(2), m.group(3)
                    month_num = MONTHS_PT.get(month_pt)
                    if month_num:
                        end_key = f"{int(day):02d}/{month_num:02d}/{year}"
                        finalizados[data] = end_key
                else:
                    finalizados[data] = None

            elif "Inclua-se em pauta" in nome and "Virtual" in comp:
                inclusoes[data] = comp

        for start_date_str, _ in iniciados.items():
            dt_inicio = _parse_date(start_date_str)

            dt_fim = pd.NaT
            lista = None
            matched_inclusao = False

            for inc_date, inc_comp in inclusoes.items():
                m_range = _RE_DATE_RANGE.search(inc_comp)
                if m_range:
                    inc_start = m_range.group(1)
                    inc_end = m_range.group(2)
                    if inc_start == start_date_str:
                        dt_fim = _parse_date(inc_end)
                        m_lista = _RE_LISTA.search(inc_comp)
                        lista = m_lista.group(1) if m_lista else None
                        matched_inclusao = True
                        break
                else:
                    m_single = _RE_DATE_SINGLE.search(inc_comp)
                    if m_single and m_single.group(1) == start_date_str:
                        m_lista = _RE_LISTA.search(inc_comp)
                        lista = m_lista.group(1) if m_lista else None
                        matched_inclusao = True
                        break

            if pd.isna(dt_fim):
                for fin_date, end_key in finalizados.items():
                    if end_key:
                        fin_end = _parse_date(end_key)
                        if not pd.isna(fin_end) and fin_end >= dt_inicio:
                            dt_fim = fin_end
                            break

            records.append({
                "processo": row["nome_processo"],
                "classe": row["classe"],
                "relator": row["relator"],
                "sessao_inicio": dt_inicio,
                "sessao_fim": dt_fim,
                "lista": lista,
            })

    if not records:
        return pd.DataFrame(columns=[
            "processo", "classe", "relator",
            "sessao_inicio", "sessao_fim", "lista",
        ])

    vs = pd.DataFrame(records)
    vs["sessao_inicio"] = pd.to_datetime(vs["sessao_inicio"], errors="coerce")
    vs["sessao_fim"] = pd.to_datetime(vs["sessao_fim"], errors="coerce")
    vs["ano_sessao"] = vs["sessao_inicio"].dt.year
    vs["mes_sessao"] = vs["sessao_inicio"].dt.to_period("M").astype(str)

    vs["sessao_label"] = vs.apply(
        lambda r: (
            f"{r['sessao_inicio'].strftime('%d/%m/%Y')} a {r['sessao_fim'].strftime('%d/%m/%Y')}"
            if pd.notna(r["sessao_fim"])
            else r["sessao_inicio"].strftime("%d/%m/%Y")
        )
        if pd.notna(r["sessao_inicio"]) else "Sem data",
        axis=1,
    )
    return vs


_DESTAQUE_NAMES = {
    "Retirado do Julgamento Virtual",
    "Processo destacado no Julgamento Virtual",
    "Destaque do(a) Ministro(a)",
    "Pedido de destaque cancelado",
}

_RE_SESSAO_DESTAQUE = re.compile(
    r"Sess[ãa]o de\s*(\d{2}/\d{2}/\d{4})\s*a\s*(\d{2}/\d{2}/\d{4})"
)


@st.cache_data(show_spinner="Extraindo destaques das sessões virtuais...")
def load_destaques(path: str) -> pd.DataFrame:
    raw = pd.read_csv(
        path,
        usecols=["nome_processo", "classe", "relator", "andamentos_lista"],
    )

    records = []
    for _, row in raw.iterrows():
        try:
            andamentos = json.loads(row["andamentos_lista"])
        except Exception:
            continue

        for a in andamentos:
            nome = a.get("nome", "")
            comp = a.get("complemento", "")
            full_text = (nome + " " + comp).lower()

            is_destaque_nome = nome in _DESTAQUE_NAMES
            is_destaque_comp = "destaque" in full_text and not is_destaque_nome

            if not is_destaque_nome and not is_destaque_comp:
                continue

            if nome in ("Retirado do Julgamento Virtual",
                        "Processo destacado no Julgamento Virtual"):
                evento = "Destaque (retirado da virtual)"
            elif nome == "Destaque do(a) Ministro(a)":
                evento = "Julgamento presencial pós-destaque"
            elif nome == "Pedido de destaque cancelado":
                evento = "Destaque cancelado"
            else:
                evento = "Menção a destaque"

            sessao = None
            m = _RE_SESSAO_DESTAQUE.search(comp)
            if m:
                sessao = f"{m.group(1)} a {m.group(2)}"

            records.append({
                "processo": row["nome_processo"],
                "classe": row["classe"],
                "relator": row["relator"],
                "data": a.get("data", ""),
                "evento": evento,
                "ministro_destaque": a.get("julgador", "NA"),
                "sessao_destaque": sessao,
                "complemento": comp[:500],
            })

    if not records:
        return pd.DataFrame(columns=[
            "processo", "classe", "relator", "data", "evento",
            "ministro_destaque", "sessao_destaque", "complemento",
        ])

    dest = pd.DataFrame(records)
    dest["data_dt"] = pd.to_datetime(
        dest["data"], format="%d/%m/%Y", errors="coerce"
    )
    dest["ano"] = dest["data_dt"].dt.year
    return dest


_REAJUSTE_TERMS = [
    "voto reajustado", "reajustou o voto", "reajuste de voto",
    "reajustou seu voto", "reajustou voto",
]


@st.cache_data(show_spinner="Extraindo votos reajustados...")
def load_votos_reajustados(path: str) -> pd.DataFrame:
    raw = pd.read_csv(
        path,
        usecols=["nome_processo", "classe", "relator", "decisões",
                 "andamentos_lista"],
    )

    records = []
    seen = set()
    for _, row in raw.iterrows():
        for col_name in ("decisões", "andamentos_lista"):
            try:
                items = json.loads(row[col_name])
            except Exception:
                continue

            for a in items:
                text = (a.get("nome", "") + " " + a.get("complemento", "")).lower()
                if not any(t in text for t in _REAJUSTE_TERMS):
                    continue

                key = (row["nome_processo"], a.get("data", ""), a.get("nome", ""))
                if key in seen:
                    continue
                seen.add(key)

                records.append({
                    "processo": row["nome_processo"],
                    "classe": row["classe"],
                    "relator": row["relator"],
                    "data": a.get("data", ""),
                    "andamento": a.get("nome", ""),
                    "julgador": a.get("julgador", "NA"),
                    "complemento": a.get("complemento", "")[:800],
                })

    if not records:
        return pd.DataFrame(columns=[
            "processo", "classe", "relator", "data",
            "andamento", "julgador", "complemento",
        ])

    vr = pd.DataFrame(records)
    vr["data_dt"] = pd.to_datetime(vr["data"], format="%d/%m/%Y", errors="coerce")
    vr["ano"] = vr["data_dt"].dt.year
    return vr


def render_virtual_sessions(vs: pd.DataFrame, dest: pd.DataFrame,
                            df_main: pd.DataFrame):
    st.header("Sessões Virtuais")

    if vs.empty:
        st.warning("Nenhuma sessão virtual encontrada nos dados.")
        return

    filtered_processes = set(df_main["nome_processo"])
    vs_f = vs[vs["processo"].isin(filtered_processes)].copy()

    if vs_f.empty:
        st.info("Nenhuma sessão virtual nos processos filtrados.")
        return

    # --- KPIs ---
    n_cases = vs_f["processo"].nunique()
    n_events = len(vs_f)
    sessions_by_start = vs_f.dropna(subset=["sessao_inicio"]).groupby("sessao_label").size()
    n_sessions = len(sessions_by_start)
    avg_per_session = sessions_by_start.mean() if n_sessions > 0 else 0

    cols = st.columns(4)
    cols[0].metric("Processos com Sessão Virtual", f"{n_cases:,}")
    cols[1].metric("Total de Inclusões", f"{n_events:,}")
    cols[2].metric("Sessões Distintas", f"{n_sessions:,}")
    cols[3].metric("Média de Processos / Sessão", f"{avg_per_session:.1f}")

    st.divider()

    # --- Cases per session over time (monthly) ---
    monthly = (
        vs_f.dropna(subset=["sessao_inicio"])
        .groupby([vs_f["sessao_inicio"].dt.to_period("M"), "classe"])
        .size()
        .reset_index(name="processos")
    )
    monthly.columns = ["mes", "classe", "processos"]
    monthly["mes"] = monthly["mes"].astype(str)

    fig = px.bar(
        monthly, x="mes", y="processos", color="classe",
        title="Processos Incluídos em Sessões Virtuais por Mês",
        color_discrete_map=COLORS,
        labels={"mes": "Mês", "processos": "Processos", "classe": "Classe"},
    )
    fig.update_layout(barmode="stack", xaxis_tickangle=-45, xaxis_dtick=3)
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)

    with c1:
        # --- Sessions per year ---
        yearly_sessions = (
            vs_f.dropna(subset=["sessao_inicio"])
            .drop_duplicates(subset=["sessao_label"])
            .groupby(vs_f["sessao_inicio"].dt.year)
            .size()
            .reset_index(name="sessoes")
        )
        yearly_sessions.columns = ["ano", "sessoes"]
        yearly_sessions["ano"] = yearly_sessions["ano"].astype(int)
        fig = px.bar(
            yearly_sessions, x="ano", y="sessoes",
            title="Quantidade de Sessões Virtuais por Ano",
            labels={"ano": "Ano", "sessoes": "Sessões"},
            text_auto=True,
        )
        fig.update_traces(marker_color="#7c3aed")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        # --- Cases per session distribution ---
        cases_per_session = (
            vs_f.dropna(subset=["sessao_inicio"])
            .groupby("sessao_label")
            .size()
            .reset_index(name="processos")
        )
        fig = px.histogram(
            cases_per_session, x="processos",
            title="Distribuição: Processos por Sessão Virtual",
            nbins=40,
            labels={"processos": "Processos na Sessão", "count": "Frequência"},
        )
        fig.update_traces(marker_color="#7c3aed")
        st.plotly_chart(fig, use_container_width=True)

    # --- Top busiest sessions ---
    st.subheader("Sessões Virtuais com Maior Volume")
    top_sessions = (
        vs_f.dropna(subset=["sessao_inicio"])
        .groupby(["sessao_label", "sessao_inicio"])
        .agg(
            processos=("processo", "count"),
            classes=("classe", lambda x: ", ".join(sorted(x.unique()))),
            lista_processos=("processo", lambda x: ", ".join(sorted(x.unique()))),
        )
        .reset_index()
        .sort_values("processos", ascending=False)
        .head(30)
    )
    top_sessions_display = top_sessions[["sessao_label", "processos", "classes"]].rename(
        columns={
            "sessao_label": "Sessão (Período)",
            "processos": "Processos",
            "classes": "Classes",
        }
    )
    st.dataframe(top_sessions_display, use_container_width=True, height=400)

    # --- Relator breakdown in virtual sessions ---
    c3, c4 = st.columns(2)

    with c3:
        rel_vs = (
            vs_f["relator"].value_counts().head(15).reset_index()
        )
        rel_vs.columns = ["Relator", "Inclusões"]
        fig = px.bar(
            rel_vs, x="Inclusões", y="Relator", orientation="h",
            title="Top 15 Relatores em Sessões Virtuais",
            color="Inclusões", color_continuous_scale="Purples",
        )
        fig.update_layout(yaxis=dict(categoryorder="total ascending"))
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    with c4:
        classe_vs = vs_f["classe"].value_counts().reset_index()
        classe_vs.columns = ["Classe", "Inclusões"]
        fig = px.pie(
            classe_vs, names="Classe", values="Inclusões",
            title="Inclusões em Sessão Virtual por Classe",
            color="Classe", color_discrete_map=COLORS,
            hole=0.4,
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    # === DESTAQUE SECTION ===
    st.divider()
    st.subheader("Destaques – Retirada de Sessão Virtual para Plenário Físico")

    dest_f = dest[dest["processo"].isin(filtered_processes)].copy()

    if dest_f.empty:
        st.info("Nenhum destaque encontrado nos processos filtrados.")
    else:
        real_destaques = dest_f[
            dest_f["evento"].isin([
                "Destaque (retirado da virtual)",
                "Julgamento presencial pós-destaque",
                "Destaque cancelado",
            ])
        ]
        n_pulled = real_destaques[
            real_destaques["evento"] == "Destaque (retirado da virtual)"
        ]["processo"].nunique()
        n_cancelled = real_destaques[
            real_destaques["evento"] == "Destaque cancelado"
        ]["processo"].nunique()
        n_physical = real_destaques[
            real_destaques["evento"] == "Julgamento presencial pós-destaque"
        ]["processo"].nunique()
        n_total_events = len(real_destaques)

        dc1, dc2, dc3, dc4 = st.columns(4)
        dc1.metric("Processos Destacados", f"{n_pulled:,}")
        dc2.metric("Destaques Cancelados", f"{n_cancelled:,}")
        dc3.metric("Julgados no Presencial", f"{n_physical:,}")
        dc4.metric("Total de Eventos", f"{n_total_events:,}")

        dc5, dc6 = st.columns(2)

        with dc5:
            min_req = real_destaques[
                (real_destaques["ministro_destaque"] != "NA")
                & real_destaques["evento"].isin([
                    "Destaque (retirado da virtual)",
                    "Destaque cancelado",
                    "Julgamento presencial pós-destaque",
                ])
            ]
            if not min_req.empty:
                req_counts = (
                    min_req["ministro_destaque"]
                    .value_counts()
                    .head(15)
                    .reset_index()
                )
                req_counts.columns = ["Ministro", "Eventos"]
                fig = px.bar(
                    req_counts, x="Eventos", y="Ministro", orientation="h",
                    title="Ministros em Eventos de Destaque",
                    color="Eventos", color_continuous_scale="Reds",
                )
                fig.update_layout(yaxis=dict(categoryorder="total ascending"))
                fig.update_coloraxes(showscale=False)
                st.plotly_chart(fig, use_container_width=True)

        with dc6:
            evento_counts = (
                real_destaques["evento"]
                .value_counts()
                .reset_index()
            )
            evento_counts.columns = ["Evento", "Quantidade"]
            fig = px.pie(
                evento_counts, names="Evento", values="Quantidade",
                title="Tipos de Evento de Destaque",
                hole=0.4,
                color="Evento",
                color_discrete_map={
                    "Destaque (retirado da virtual)": "#dc2626",
                    "Destaque cancelado": "#6b7280",
                    "Julgamento presencial pós-destaque": "#2563eb",
                },
            )
            fig.update_traces(textinfo="value+percent")
            st.plotly_chart(fig, use_container_width=True)

        dest_yearly = (
            real_destaques.dropna(subset=["ano"])
            .groupby(["ano", "evento"])
            .size()
            .reset_index(name="quantidade")
        )
        if not dest_yearly.empty:
            dest_yearly["ano"] = dest_yearly["ano"].astype(int)
            fig = px.bar(
                dest_yearly, x="ano", y="quantidade", color="evento",
                title="Eventos de Destaque por Ano",
                color_discrete_map={
                    "Destaque (retirado da virtual)": "#dc2626",
                    "Destaque cancelado": "#6b7280",
                    "Julgamento presencial pós-destaque": "#2563eb",
                },
                labels={"ano": "Ano", "quantidade": "Eventos", "evento": "Tipo"},
            )
            fig.update_layout(barmode="stack")
            st.plotly_chart(fig, use_container_width=True)

        st.caption("Tabela de destaques")
        dest_display = real_destaques[[
            "processo", "classe", "relator", "data", "evento",
            "ministro_destaque", "sessao_destaque",
        ]].rename(columns={
            "processo": "Processo",
            "classe": "Classe",
            "relator": "Relator",
            "data": "Data",
            "evento": "Evento",
            "ministro_destaque": "Ministro",
            "sessao_destaque": "Sessão Virtual",
        }).sort_values("Data", ascending=False)
        st.dataframe(dest_display, use_container_width=True, height=400)

    # --- Detailed session explorer ---
    st.divider()
    st.subheader("Explorar Sessões")
    search_session = st.text_input(
        "Buscar por processo ou relator:", "", key="vs_search"
    )
    explorer = vs_f[["processo", "classe", "relator", "sessao_label", "lista"]].rename(
        columns={
            "processo": "Processo",
            "classe": "Classe",
            "relator": "Relator",
            "sessao_label": "Sessão (Período)",
            "lista": "Lista",
        }
    ).sort_values("Sessão (Período)", ascending=False)

    if search_session:
        mask = (
            explorer["Processo"].str.contains(search_session, case=False, na=False)
            | explorer["Relator"].str.contains(search_session, case=False, na=False)
        )
        explorer = explorer[mask]

    st.caption(f"{len(explorer):,} inclusões em sessões virtuais")
    st.dataframe(explorer, use_container_width=True, height=500)


def render_votos_reajustados(vr: pd.DataFrame, df_main: pd.DataFrame):
    st.header("Votos Reajustados")

    if vr.empty:
        st.warning("Nenhum voto reajustado encontrado nos dados.")
        return

    filtered_processes = set(df_main["nome_processo"])
    vr_f = vr[vr["processo"].isin(filtered_processes)].copy()

    if vr_f.empty:
        st.info("Nenhum voto reajustado nos processos filtrados.")
        return

    n_cases = vr_f["processo"].nunique()
    n_events = len(vr_f)

    cols = st.columns(4)
    cols[0].metric("Processos com Voto Reajustado", f"{n_cases:,}")
    cols[1].metric("Total de Ocorrências", f"{n_events:,}")
    pct = n_cases / len(df_main) * 100 if len(df_main) > 0 else 0
    cols[2].metric("% do Total de Processos", f"{pct:.2f}%")
    n_relatores = vr_f["relator"].nunique()
    cols[3].metric("Relatores Envolvidos", f"{n_relatores:,}")

    st.divider()

    c1, c2 = st.columns(2)

    with c1:
        yearly = (
            vr_f.dropna(subset=["ano"])
            .groupby("ano")
            .size()
            .reset_index(name="ocorrencias")
        )
        if not yearly.empty:
            yearly["ano"] = yearly["ano"].astype(int)
            fig = px.bar(
                yearly, x="ano", y="ocorrencias",
                title="Votos Reajustados por Ano",
                labels={"ano": "Ano", "ocorrencias": "Ocorrências"},
                text_auto=True,
            )
            fig.update_traces(marker_color="#0891b2")
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        rel_counts = vr_f["relator"].value_counts().reset_index()
        rel_counts.columns = ["Relator", "Ocorrências"]
        fig = px.bar(
            rel_counts, x="Ocorrências", y="Relator", orientation="h",
            title="Votos Reajustados por Relator",
            color="Ocorrências", color_continuous_scale="Teal",
        )
        fig.update_layout(yaxis=dict(categoryorder="total ascending"))
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)

    with c3:
        classe_counts = vr_f["classe"].value_counts().reset_index()
        classe_counts.columns = ["Classe", "Ocorrências"]
        fig = px.pie(
            classe_counts, names="Classe", values="Ocorrências",
            title="Votos Reajustados por Classe",
            color="Classe", color_discrete_map=COLORS,
            hole=0.4,
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with c4:
        tipo_counts = vr_f["andamento"].value_counts().reset_index()
        tipo_counts.columns = ["Tipo de Decisão", "Ocorrências"]
        fig = px.bar(
            tipo_counts, x="Ocorrências", y="Tipo de Decisão", orientation="h",
            title="Em Que Tipo de Decisão Ocorre o Reajuste?",
            color="Ocorrências", color_continuous_scale="Teal",
        )
        fig.update_layout(yaxis=dict(categoryorder="total ascending"))
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    julgadores = vr_f[vr_f["julgador"] != "NA"]
    if not julgadores.empty:
        julg_counts = julgadores["julgador"].value_counts().head(15).reset_index()
        julg_counts.columns = ["Órgão Julgador", "Ocorrências"]
        fig = px.bar(
            julg_counts, x="Ocorrências", y="Órgão Julgador", orientation="h",
            title="Órgão Julgador nas Decisões com Reajuste",
            color="Ocorrências", color_continuous_scale="Teal",
        )
        fig.update_layout(yaxis=dict(categoryorder="total ascending"))
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Detalhamento dos Votos Reajustados")
    search_vr = st.text_input(
        "Buscar por processo, relator ou texto:", "", key="vr_search"
    )
    vr_display = vr_f[[
        "processo", "classe", "relator", "data", "andamento",
        "julgador", "complemento",
    ]].rename(columns={
        "processo": "Processo",
        "classe": "Classe",
        "relator": "Relator",
        "data": "Data",
        "andamento": "Decisão",
        "julgador": "Órgão Julgador",
        "complemento": "Texto",
    }).sort_values("Data", ascending=False)

    if search_vr:
        mask = (
            vr_display["Processo"].str.contains(search_vr, case=False, na=False)
            | vr_display["Relator"].str.contains(search_vr, case=False, na=False)
            | vr_display["Texto"].str.contains(search_vr, case=False, na=False)
        )
        vr_display = vr_display[mask]

    st.caption(f"{len(vr_display):,} ocorrências de votos reajustados")
    st.dataframe(vr_display, use_container_width=True, height=500)


# --- Vista ---

_VISTA_REQUEST_NAMES = {
    "Vista ao(à) Ministro(a)",
    "VISTA AO MINISTRO",
    "VISTA À MINISTRA",
    "Vista",
    "VISTA",
}

_VISTA_RETURN_NAMES = {
    "Vista - Devolução dos autos para julgamento",
    "VISTA - DEVOLUÇÃO DOS AUTOS PARA JULGAMENTO",
}

_VISTA_RENEWED_NAMES = {
    "VISTA RENOVADA JUSTIFICADAMENTE, A PEDIDO, POR 10 DIAS",
}

_RE_PEDIDO_VISTA_MIN = re.compile(
    r"(?:PEDIDO DE )?VISTA D[OA]S?\s*(?:SR\.?\s*)?(?:SENHOR(?:A)?\s*)?MIN(?:ISTRO|ISTRA|\.)\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]+?)(?:\.|,|\(|$)",
    re.IGNORECASE,
)


def _extract_vista_minister(nome: str, julgador: str, complemento: str) -> str:
    if julgador and julgador != "NA":
        return re.sub(r"^MIN\.\s+", "", julgador, flags=re.IGNORECASE)

    m = _RE_PEDIDO_VISTA_MIN.search(complemento)
    if m:
        return m.group(1).strip().rstrip(",. ")
    return "Não identificado"


@st.cache_data(show_spinner="Extraindo pedidos de vista...")
def load_vistas(path: str) -> pd.DataFrame:
    raw = pd.read_csv(
        path,
        usecols=["nome_processo", "classe", "relator", "andamentos_lista"],
    )

    records = []
    for _, row in raw.iterrows():
        try:
            andamentos = json.loads(row["andamentos_lista"])
        except Exception:
            continue

        for a in andamentos:
            nome = a.get("nome", "")
            comp = a.get("complemento", "")
            julg = a.get("julgador", "")
            data = a.get("data", "")

            is_suspended_vista = (
                nome == "Suspenso o julgamento"
                and "vista" in comp.lower()
            )

            if nome in _VISTA_REQUEST_NAMES:
                evento = "Pedido de Vista"
                ministro = _extract_vista_minister(nome, julg, comp)
            elif nome in _VISTA_RETURN_NAMES:
                evento = "Devolução (retorno)"
                ministro = _extract_vista_minister(nome, julg, comp)
            elif nome in _VISTA_RENEWED_NAMES:
                evento = "Vista Renovada"
                ministro = _extract_vista_minister(nome, julg, comp)
            elif is_suspended_vista:
                evento = "Julgamento Suspenso (vista)"
                ministro = _extract_vista_minister(nome, julg, comp)
            else:
                continue

            is_virtual = "SESSÃO VIRTUAL" in julg.upper() if julg else False

            records.append({
                "processo": row["nome_processo"],
                "classe": row["classe"],
                "relator": row["relator"],
                "data": data,
                "evento": evento,
                "ministro_vista": ministro,
                "sessao_virtual": is_virtual,
                "complemento": comp[:500],
            })

    if not records:
        return pd.DataFrame(columns=[
            "processo", "classe", "relator", "data", "evento",
            "ministro_vista", "sessao_virtual", "complemento",
        ])

    vt = pd.DataFrame(records)
    vt["data_dt"] = pd.to_datetime(vt["data"], format="%d/%m/%Y", errors="coerce")
    vt["ano"] = vt["data_dt"].dt.year
    return vt


def render_vistas(vt: pd.DataFrame, df_main: pd.DataFrame):
    st.header("Pedidos de Vista")

    if vt.empty:
        st.warning("Nenhum pedido de vista encontrado.")
        return

    filtered_processes = set(df_main["nome_processo"])
    vt_f = vt[vt["processo"].isin(filtered_processes)].copy()

    if vt_f.empty:
        st.info("Nenhum pedido de vista nos processos filtrados.")
        return

    pedidos = vt_f[vt_f["evento"] == "Pedido de Vista"]
    devolucoes = vt_f[vt_f["evento"] == "Devolução (retorno)"]
    renovadas = vt_f[vt_f["evento"] == "Vista Renovada"]
    suspensos = vt_f[vt_f["evento"] == "Julgamento Suspenso (vista)"]

    cols = st.columns(5)
    cols[0].metric("Pedidos de Vista", f"{len(pedidos):,}")
    cols[1].metric("Devoluções", f"{len(devolucoes):,}")
    cols[2].metric("Vistas Renovadas", f"{len(renovadas):,}")
    cols[3].metric("Julgamentos Suspensos", f"{len(suspensos):,}")
    cols[4].metric("Processos Envolvidos", f"{vt_f['processo'].nunique():,}")

    st.divider()

    # --- Timeline ---
    yearly = (
        vt_f.dropna(subset=["ano"])
        .groupby(["ano", "evento"])
        .size()
        .reset_index(name="quantidade")
    )
    if not yearly.empty:
        yearly["ano"] = yearly["ano"].astype(int)
        fig = px.bar(
            yearly, x="ano", y="quantidade", color="evento",
            title="Eventos de Vista por Ano",
            color_discrete_map={
                "Pedido de Vista": "#dc2626",
                "Devolução (retorno)": "#2563eb",
                "Vista Renovada": "#d97706",
                "Julgamento Suspenso (vista)": "#6b7280",
            },
            labels={"ano": "Ano", "quantidade": "Eventos", "evento": "Tipo"},
        )
        fig.update_layout(barmode="stack")
        st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)

    with c1:
        # --- Who requests vistas the most ---
        min_counts = (
            pedidos["ministro_vista"]
            .value_counts()
            .head(20)
            .reset_index()
        )
        min_counts.columns = ["Ministro", "Pedidos"]
        fig = px.bar(
            min_counts, x="Pedidos", y="Ministro", orientation="h",
            title="Ministros que Mais Pedem Vista",
            color="Pedidos", color_continuous_scale="Reds",
        )
        fig.update_layout(yaxis=dict(categoryorder="total ascending"))
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        # --- Cases with most vistas ---
        proc_counts = (
            pedidos["processo"]
            .value_counts()
            .head(20)
            .reset_index()
        )
        proc_counts.columns = ["Processo", "Pedidos de Vista"]
        fig = px.bar(
            proc_counts, x="Pedidos de Vista", y="Processo", orientation="h",
            title="Processos com Mais Pedidos de Vista",
            color="Pedidos de Vista", color_continuous_scale="Oranges",
        )
        fig.update_layout(yaxis=dict(categoryorder="total ascending"))
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)

    with c3:
        classe_counts = pedidos["classe"].value_counts().reset_index()
        classe_counts.columns = ["Classe", "Pedidos"]
        fig = px.pie(
            classe_counts, names="Classe", values="Pedidos",
            title="Pedidos de Vista por Classe",
            color="Classe", color_discrete_map=COLORS,
            hole=0.4,
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with c4:
        virtual_counts = pedidos["sessao_virtual"].value_counts().reset_index()
        virtual_counts.columns = ["Virtual", "Pedidos"]
        virtual_counts["Virtual"] = virtual_counts["Virtual"].map(
            {True: "Sessão Virtual", False: "Sessão Presencial"}
        )
        fig = px.pie(
            virtual_counts, names="Virtual", values="Pedidos",
            title="Pedidos de Vista: Virtual vs Presencial",
            color="Virtual",
            color_discrete_map={
                "Sessão Virtual": "#7c3aed",
                "Sessão Presencial": "#0891b2",
            },
            hole=0.4,
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    # --- Duration analysis: pair pedido → devolução ---
    st.subheader("Duração das Vistas (Pedido → Devolução)")
    durations = []
    for proc in pedidos["processo"].unique():
        proc_pedidos = pedidos[pedidos["processo"] == proc].sort_values("data_dt")
        proc_devols = devolucoes[devolucoes["processo"] == proc].sort_values("data_dt")
        for _, ped in proc_pedidos.iterrows():
            if pd.isna(ped["data_dt"]):
                continue
            later_devols = proc_devols[proc_devols["data_dt"] > ped["data_dt"]]
            if not later_devols.empty:
                dev = later_devols.iloc[0]
                days = (dev["data_dt"] - ped["data_dt"]).days
                if 0 < days < 5000:
                    durations.append({
                        "processo": proc,
                        "classe": ped["classe"],
                        "ministro": ped["ministro_vista"],
                        "data_pedido": ped["data_dt"],
                        "data_devolucao": dev["data_dt"],
                        "dias": days,
                    })

    if durations:
        dur_df = pd.DataFrame(durations)
        dc1, dc2, dc3 = st.columns(3)
        dc1.metric("Vistas Pareadas", f"{len(dur_df):,}")
        dc2.metric("Mediana (dias)", f"{dur_df['dias'].median():.0f}")
        dc3.metric("Média (dias)", f"{dur_df['dias'].mean():.0f}")

        fig = px.histogram(
            dur_df, x="dias", nbins=50,
            title="Distribuição da Duração das Vistas (em dias)",
            labels={"dias": "Dias", "count": "Frequência"},
        )
        fig.update_traces(marker_color="#dc2626")
        st.plotly_chart(fig, use_container_width=True)

        min_dur = (
            dur_df.groupby("ministro")
            .agg(mediana=("dias", "median"), total=("dias", "count"))
            .reset_index()
        )
        min_dur = min_dur[min_dur["total"] >= 3].sort_values("mediana", ascending=True)
        if not min_dur.empty:
            fig = px.bar(
                min_dur, x="mediana", y="ministro", orientation="h",
                title="Duração Mediana da Vista por Ministro (mín. 3 vistas)",
                labels={"mediana": "Dias (mediana)", "ministro": "Ministro"},
                hover_data=["total"],
                color="mediana",
                color_continuous_scale="RdYlGn_r",
            )
            fig.update_layout(yaxis=dict(categoryorder="total ascending"))
            fig.update_coloraxes(showscale=False)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Não foi possível parear pedidos e devoluções para calcular duração.")

    # --- Detailed explorer ---
    st.subheader("Explorar Pedidos de Vista")
    search_vt = st.text_input(
        "Buscar por processo, ministro ou texto:", "", key="vt_search"
    )
    vt_display = vt_f[[
        "processo", "classe", "relator", "data", "evento",
        "ministro_vista", "sessao_virtual", "complemento",
    ]].rename(columns={
        "processo": "Processo",
        "classe": "Classe",
        "relator": "Relator",
        "data": "Data",
        "evento": "Evento",
        "ministro_vista": "Ministro",
        "sessao_virtual": "Sessão Virtual",
        "complemento": "Texto",
    }).sort_values("Data", ascending=False)

    if search_vt:
        mask = (
            vt_display["Processo"].str.contains(search_vt, case=False, na=False)
            | vt_display["Ministro"].str.contains(search_vt, case=False, na=False)
            | vt_display["Texto"].str.contains(search_vt, case=False, na=False)
        )
        vt_display = vt_display[mask]

    st.caption(f"{len(vt_display):,} eventos de vista")
    st.dataframe(vt_display, use_container_width=True, height=500)


def render_kpi_row(df: pd.DataFrame):
    cols = st.columns(6)
    cols[0].metric("Total de Processos", f"{len(df):,}")
    cols[1].metric("ADI", f"{(df['classe'] == 'ADI').sum():,}")
    cols[2].metric("ADPF", f"{(df['classe'] == 'ADPF').sum():,}")
    cols[3].metric("ADC", f"{(df['classe'] == 'ADC').sum():,}")
    cols[4].metric("ADO", f"{(df['classe'] == 'ADO').sum():,}")
    pct_active = (df["status_processo"] == "Em andamento").mean() * 100
    cols[5].metric("Em Andamento", f"{pct_active:.1f}%")


def render_overview(df: pd.DataFrame):
    st.header("Visão Geral")
    render_kpi_row(df)
    st.divider()

    c1, c2 = st.columns(2)

    with c1:
        status_df = df["status_processo"].value_counts().reset_index()
        status_df.columns = ["Status", "Quantidade"]
        fig = px.pie(
            status_df, names="Status", values="Quantidade",
            title="Status dos Processos",
            color="Status",
            color_discrete_map={"Finalizado": "#6b7280", "Em andamento": "#2563eb"},
            hole=0.4,
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        classe_df = df["classe"].value_counts().reset_index()
        classe_df.columns = ["Classe", "Quantidade"]
        fig = px.bar(
            classe_df, x="Classe", y="Quantidade",
            title="Processos por Classe",
            color="Classe", color_discrete_map=COLORS,
            text_auto=True,
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)

    with c3:
        tipo_df = df["tipo_processo"].value_counts().reset_index()
        tipo_df.columns = ["Tipo", "Quantidade"]
        fig = px.pie(
            tipo_df, names="Tipo", values="Quantidade",
            title="Tipo de Processo",
            color="Tipo",
            color_discrete_map={"Físico": "#9333ea", "Eletrônico": "#0891b2"},
            hole=0.4,
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with c4:
        tipo_lim = df["tipo_liminar"].value_counts().reset_index()
        tipo_lim.columns = ["Tipo", "Quantidade"]
        fig = px.pie(
            tipo_lim, names="Tipo", values="Quantidade",
            title="Classificação Liminar por Processo (1 por caso)",
            color="Tipo",
            color_discrete_map={
                "MC (colegiada)": "#2563eb",
                "MC-Ref (mono → referendada)": "#7c3aed",
                "Monocrática (sem referendo)": "#d97706",
                "TPI (monocrática)": "#0891b2",
                "Sem decisão liminar": "#6b7280",
            },
            hole=0.4,
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    # --- Multiple-decisions transparency ---
    with_decision = df[df["tipo_liminar"] != "Sem decisão liminar"]
    multi_dec = df[df["n_decisoes_liminar"] >= 2]
    total_events = int(df["n_decisoes_liminar"].sum())
    n_multi = len(multi_dec)

    if n_multi > 0:
        st.divider()
        st.subheader("Decisões Liminares – Visão por Processo vs. por Evento")
        st.info(
            f"**Atenção:** {n_multi} processos ({n_multi/len(df)*100:.1f}%) possuem "
            f"**múltiplas decisões liminares** (ex.: liminar deferida + referendo, ou "
            f"liminares renovadas). O total de eventos individuais é "
            f"**{total_events:,}**, contra {len(with_decision):,} processos com ao "
            f"menos uma decisão. Os gráficos acima atribuem **uma classificação por "
            f"processo** (a trajetória predominante). A seção abaixo mostra a "
            f"distribuição de eventos."
        )

        lm1, lm2, lm3, lm4 = st.columns(4)
        lm1.metric("Processos com Decisão", f"{len(with_decision):,}")
        lm2.metric("Total de Eventos Liminares", f"{total_events:,}")
        lm3.metric("Processos c/ Múltiplas Decisões", f"{n_multi:,}")
        lm4.metric(
            "Máx. Decisões em 1 Processo",
            f"{int(df['n_decisoes_liminar'].max())}",
        )

        cm1, cm2 = st.columns(2)
        with cm1:
            dec_dist = (
                multi_dec["n_decisoes_liminar"]
                .value_counts()
                .sort_index()
                .reset_index()
            )
            dec_dist.columns = ["Decisões no Processo", "Processos"]
            fig = px.bar(
                dec_dist, x="Decisões no Processo", y="Processos",
                title="Distribuição: Processos com 2+ Decisões Liminares",
                text_auto=True,
            )
            fig.update_traces(marker_color="#7c3aed")
            st.plotly_chart(fig, use_container_width=True)

        with cm2:
            multi_by_class = (
                multi_dec.groupby("classe")["n_decisoes_liminar"]
                .sum()
                .reset_index()
            )
            multi_by_class.columns = ["Classe", "Total Eventos"]
            fig = px.bar(
                multi_by_class, x="Classe", y="Total Eventos",
                title="Eventos Liminares Múltiplos por Classe",
                color="Classe", color_discrete_map=COLORS,
                text_auto=True,
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        with st.expander("Processos com Múltiplas Decisões Liminares"):
            show_cols = [
                "nome_processo", "classe", "relator", "tipo_liminar",
                "resultado_liminar", "n_decisoes_liminar",
            ]
            display_df = (
                multi_dec[show_cols]
                .sort_values("n_decisoes_liminar", ascending=False)
                .rename(columns={
                    "nome_processo": "Processo",
                    "classe": "Classe",
                    "relator": "Relator",
                    "tipo_liminar": "Classificação",
                    "resultado_liminar": "Resultado",
                    "n_decisoes_liminar": "Nº Decisões",
                })
            )
            st.dataframe(display_df, use_container_width=True, height=400)

    st.divider()

    if not with_decision.empty:
        c5, c6 = st.columns(2)
        with c5:
            res_counts = with_decision["resultado_liminar"].value_counts().reset_index()
            res_counts.columns = ["Resultado", "Quantidade"]
            fig = px.pie(
                res_counts, names="Resultado", values="Quantidade",
                title="Resultado da Liminar (1 por processo)",
                color="Resultado",
                color_discrete_map={
                    "Deferida": "#16a34a",
                    "Deferida em parte": "#84cc16",
                    "Indeferida": "#dc2626",
                    "Não referendada": "#f97316",
                },
                hole=0.4,
            )
            fig.update_traces(textinfo="value+percent")
            st.plotly_chart(fig, use_container_width=True)

        with c6:
            cross = (
                with_decision.groupby(["tipo_liminar", "resultado_liminar"])
                .size()
                .reset_index(name="quantidade")
            )
            fig = px.bar(
                cross, x="tipo_liminar", y="quantidade", color="resultado_liminar",
                title="Tipo × Resultado da Liminar (1 por processo)",
                color_discrete_map={
                    "Deferida": "#16a34a",
                    "Deferida em parte": "#84cc16",
                    "Indeferida": "#dc2626",
                    "Não referendada": "#f97316",
                },
                labels={
                    "tipo_liminar": "Tipo",
                    "quantidade": "Processos",
                    "resultado_liminar": "Resultado",
                },
            )
            fig.update_layout(barmode="stack", xaxis_tickangle=-25)
            st.plotly_chart(fig, use_container_width=True)

        # --- Liminar type per year (stacked bar) ---
        lim_year = (
            df.dropna(subset=["ano"])
            .groupby(["ano", "tipo_liminar"])
            .size()
            .reset_index(name="quantidade")
        )
        lim_year["ano"] = lim_year["ano"].astype(int)
        fig = px.bar(
            lim_year, x="ano", y="quantidade", color="tipo_liminar",
            title="Tipo de Decisão Liminar por Ano de Protocolo",
            color_discrete_map={
                "MC (colegiada)": "#2563eb",
                "MC-Ref (mono → referendada)": "#7c3aed",
                "Monocrática (sem referendo)": "#d97706",
                "TPI (monocrática)": "#0891b2",
                "Sem decisão liminar": "#6b7280",
            },
            labels={
                "ano": "Ano",
                "quantidade": "Processos",
                "tipo_liminar": "Tipo Liminar",
            },
        )
        fig.update_layout(barmode="stack", xaxis_dtick=2, xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

        # --- Resultado per year (only cases with a decision) ---
        res_year = (
            with_decision.dropna(subset=["ano"])
            .groupby(["ano", "resultado_liminar"])
            .size()
            .reset_index(name="quantidade")
        )
        res_year["ano"] = res_year["ano"].astype(int)
        fig = px.bar(
            res_year, x="ano", y="quantidade", color="resultado_liminar",
            title="Resultado da Liminar por Ano (casos com decisão)",
            color_discrete_map={
                "Deferida": "#16a34a",
                "Deferida em parte": "#84cc16",
                "Indeferida": "#dc2626",
                "Não referendada": "#f97316",
            },
            labels={
                "ano": "Ano",
                "quantidade": "Processos",
                "resultado_liminar": "Resultado",
            },
        )
        fig.update_layout(barmode="stack", xaxis_dtick=2, xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)


def render_temporal(df: pd.DataFrame):
    st.header("Análise Temporal")

    yearly = (
        df.groupby(["ano", "classe"])
        .size()
        .reset_index(name="quantidade")
    )
    yearly = yearly.dropna(subset=["ano"])
    yearly["ano"] = yearly["ano"].astype(int)

    fig = px.bar(
        yearly, x="ano", y="quantidade", color="classe",
        title="Processos Protocolados por Ano",
        color_discrete_map=COLORS,
        labels={"ano": "Ano", "quantidade": "Processos", "classe": "Classe"},
    )
    fig.update_layout(barmode="stack", xaxis_dtick=2)
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)

    with c1:
        cumulative = (
            df.dropna(subset=["ano"])
            .sort_values("ano")
            .groupby("ano")
            .size()
            .cumsum()
            .reset_index(name="acumulado")
        )
        fig = px.area(
            cumulative, x="ano", y="acumulado",
            title="Acúmulo de Processos ao Longo do Tempo",
            labels={"ano": "Ano", "acumulado": "Total Acumulado"},
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        status_year = (
            df.dropna(subset=["ano"])
            .groupby(["ano", "status_processo"])
            .size()
            .reset_index(name="quantidade")
        )
        status_year["ano"] = status_year["ano"].astype(int)
        fig = px.bar(
            status_year, x="ano", y="quantidade", color="status_processo",
            title="Status por Ano de Protocolo",
            color_discrete_map={"Finalizado": "#6b7280", "Em andamento": "#2563eb"},
            labels={"ano": "Ano", "quantidade": "Processos", "status_processo": "Status"},
        )
        fig.update_layout(barmode="stack", xaxis_dtick=5)
        st.plotly_chart(fig, use_container_width=True)

    tipo_year = (
        df.dropna(subset=["ano"])
        .groupby(["ano", "tipo_processo"])
        .size()
        .reset_index(name="quantidade")
    )
    tipo_year["ano"] = tipo_year["ano"].astype(int)
    fig = px.area(
        tipo_year, x="ano", y="quantidade", color="tipo_processo",
        title="Transição: Processos Físicos → Eletrônicos",
        color_discrete_map={"Físico": "#9333ea", "Eletrônico": "#0891b2"},
        labels={"ano": "Ano", "quantidade": "Processos", "tipo_processo": "Tipo"},
    )
    st.plotly_chart(fig, use_container_width=True)


def render_geographic(df: pd.DataFrame):
    st.header("Distribuição Geográfica")

    geo_df = (
        df[df["origem_valida"].notna()]
        .groupby("origem_valida")
        .size()
        .reset_index(name="quantidade")
    )
    geo_df.columns = ["UF", "quantidade"]
    geo_df["Estado"] = geo_df["UF"].map(UF_NAMES)
    geo_df = geo_df.sort_values("quantidade", ascending=True)

    fig = px.bar(
        geo_df, x="quantidade", y="UF", orientation="h",
        title="Processos por Estado de Origem",
        color="quantidade",
        color_continuous_scale="Blues",
        labels={"quantidade": "Processos", "UF": "Estado"},
        hover_data=["Estado"],
    )
    fig.update_layout(height=700, yaxis=dict(categoryorder="total ascending"))
    fig.update_coloraxes(showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        top_states = geo_df.nlargest(10, "quantidade")["UF"].tolist()
        geo_class = (
            df[df["origem_valida"].isin(top_states)]
            .groupby(["origem_valida", "classe"])
            .size()
            .reset_index(name="quantidade")
        )
        fig = px.bar(
            geo_class, x="origem_valida", y="quantidade", color="classe",
            title="Top 10 Estados – por Classe",
            color_discrete_map=COLORS,
            labels={"origem_valida": "UF", "quantidade": "Processos", "classe": "Classe"},
        )
        fig.update_layout(barmode="stack")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        geo_status = (
            df[df["origem_valida"].isin(top_states)]
            .groupby(["origem_valida", "status_processo"])
            .size()
            .reset_index(name="quantidade")
        )
        fig = px.bar(
            geo_status, x="origem_valida", y="quantidade", color="status_processo",
            title="Top 10 Estados – por Status",
            color_discrete_map={"Finalizado": "#6b7280", "Em andamento": "#2563eb"},
            labels={"origem_valida": "UF", "quantidade": "Processos", "status_processo": "Status"},
        )
        fig.update_layout(barmode="stack")
        st.plotly_chart(fig, use_container_width=True)


def render_justices(df: pd.DataFrame):
    st.header("Relatores (Ministros)")

    rel_df = (
        df["relator"].value_counts()
        .reset_index()
    )
    rel_df.columns = ["Relator", "Processos"]

    fig = px.bar(
        rel_df, x="Processos", y="Relator", orientation="h",
        title="Distribuição de Processos por Relator",
        color="Processos",
        color_continuous_scale="Reds",
    )
    fig.update_layout(
        height=max(500, len(rel_df) * 22),
        yaxis=dict(categoryorder="total ascending"),
    )
    fig.update_coloraxes(showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)

    with c1:
        top_rel = rel_df.nlargest(12, "Processos")["Relator"].tolist()
        rel_class = (
            df[df["relator"].isin(top_rel)]
            .groupby(["relator", "classe"])
            .size()
            .reset_index(name="quantidade")
        )
        fig = px.bar(
            rel_class, x="relator", y="quantidade", color="classe",
            title="Top 12 Relatores – por Classe",
            color_discrete_map=COLORS,
            labels={"relator": "Relator", "quantidade": "Processos", "classe": "Classe"},
        )
        fig.update_layout(barmode="stack", xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        rel_status = (
            df[df["relator"].isin(top_rel)]
            .groupby(["relator", "status_processo"])
            .size()
            .reset_index(name="quantidade")
        )
        fig = px.bar(
            rel_status, x="relator", y="quantidade", color="status_processo",
            title="Top 12 Relatores – Finalizados vs Em Andamento",
            color_discrete_map={"Finalizado": "#6b7280", "Em andamento": "#2563eb"},
            labels={"relator": "Relator", "quantidade": "Processos", "status_processo": "Status"},
        )
        fig.update_layout(barmode="stack", xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Atividade dos Relatores ao Longo do Tempo")
    selected_justices = st.multiselect(
        "Selecione relatores para comparar:",
        options=rel_df["Relator"].tolist(),
        default=rel_df.nlargest(5, "Processos")["Relator"].tolist(),
    )
    if selected_justices:
        rel_time = (
            df[df["relator"].isin(selected_justices)]
            .dropna(subset=["ano"])
            .groupby(["ano", "relator"])
            .size()
            .reset_index(name="quantidade")
        )
        rel_time["ano"] = rel_time["ano"].astype(int)
        fig = px.line(
            rel_time, x="ano", y="quantidade", color="relator",
            title="Processos Distribuídos por Ano",
            labels={"ano": "Ano", "quantidade": "Processos", "relator": "Relator"},
            markers=True,
        )
        st.plotly_chart(fig, use_container_width=True)


def render_petitioners(df: pd.DataFrame):
    st.header("Autores / Requerentes")

    cat_df = (
        df["categoria_autor"].value_counts()
        .reset_index()
    )
    cat_df.columns = ["Categoria", "Processos"]

    c1, c2 = st.columns(2)

    with c1:
        fig = px.pie(
            cat_df, names="Categoria", values="Processos",
            title="Processos por Categoria de Autor",
            hole=0.35,
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        top_authors = (
            df["autor1"].value_counts().head(15).reset_index()
        )
        top_authors.columns = ["Autor", "Processos"]
        fig = px.bar(
            top_authors, x="Processos", y="Autor", orientation="h",
            title="Top 15 Autores (Requerentes)",
            color="Processos", color_continuous_scale="Oranges",
        )
        fig.update_layout(yaxis=dict(categoryorder="total ascending"))
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    cat_time = (
        df.dropna(subset=["ano"])
        .groupby(["ano", "categoria_autor"])
        .size()
        .reset_index(name="quantidade")
    )
    cat_time["ano"] = cat_time["ano"].astype(int)
    fig = px.area(
        cat_time, x="ano", y="quantidade", color="categoria_autor",
        title="Evolução: Quem Provoca o STF ao Longo do Tempo?",
        labels={"ano": "Ano", "quantidade": "Processos", "categoria_autor": "Categoria"},
    )
    fig.update_layout(xaxis_dtick=2)
    st.plotly_chart(fig, use_container_width=True)


def render_complexity(df: pd.DataFrame):
    st.header("Complexidade Processual")

    c1, c2 = st.columns(2)
    with c1:
        fig = px.histogram(
            df, x="len(andamentos_lista)", color="classe",
            title="Distribuição de Andamentos por Processo",
            color_discrete_map=COLORS,
            nbins=60, barmode="overlay", opacity=0.7,
            labels={"len(andamentos_lista)": "Nº de Andamentos", "classe": "Classe"},
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        fig = px.histogram(
            df, x="len(partes_total)", color="classe",
            title="Distribuição de Partes por Processo",
            color_discrete_map=COLORS,
            nbins=50, barmode="overlay", opacity=0.7,
            labels={"len(partes_total)": "Nº de Partes", "classe": "Classe"},
        )
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        fig = px.box(
            df, x="classe", y="len(andamentos_lista)", color="classe",
            title="Andamentos por Classe (Box Plot)",
            color_discrete_map=COLORS,
            labels={"classe": "Classe", "len(andamentos_lista)": "Nº de Andamentos"},
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with c4:
        fig = px.box(
            df, x="classe", y="len(decisões)", color="classe",
            title="Decisões por Classe (Box Plot)",
            color_discrete_map=COLORS,
            labels={"classe": "Classe", "len(decisões)": "Nº de Decisões"},
        )
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
            fill="toself",
            name=row["classe"],
            line=dict(color=COLORS.get(row["classe"])),
        ))
    fig.update_layout(
        title="Perfil de Complexidade por Classe (Medianas)",
        polar=dict(radialaxis=dict(visible=True)),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_explorer(df: pd.DataFrame):
    st.header("Explorar Processos")

    c1, c2, c3 = st.columns(3)
    with c1:
        search = st.text_input("Buscar por nome do processo ou autor:", "")
    with c2:
        classe_filter = st.multiselect(
            "Classe:", df["classe"].unique().tolist(),
            default=df["classe"].unique().tolist(),
        )
    with c3:
        status_filter = st.multiselect(
            "Status:", df["status_processo"].unique().tolist(),
            default=df["status_processo"].unique().tolist(),
        )

    filtered = df[
        df["classe"].isin(classe_filter) & df["status_processo"].isin(status_filter)
    ]

    if search:
        mask = (
            filtered["nome_processo"].str.contains(search, case=False, na=False)
            | filtered["autor1"].str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]

    display_cols = [
        "nome_processo", "classe_extenso", "relator", "autor1",
        "origem", "data_protocolo", "status_processo", "tipo_processo",
        "tem_liminar", "len(andamentos_lista)", "len(decisões)",
        "len(partes_total)",
    ]
    renamed = {
        "nome_processo": "Processo",
        "classe_extenso": "Classe",
        "relator": "Relator",
        "autor1": "Autor Principal",
        "origem": "UF",
        "data_protocolo": "Protocolo",
        "status_processo": "Status",
        "tipo_processo": "Tipo",
        "tem_liminar": "Liminar",
        "len(andamentos_lista)": "Andamentos",
        "len(decisões)": "Decisões",
        "len(partes_total)": "Partes",
    }

    st.caption(f"Exibindo {len(filtered):,} de {len(df):,} processos")
    st.dataframe(
        filtered[display_cols].rename(columns=renamed).sort_values(
            "Protocolo", ascending=False
        ),
        use_container_width=True,
        height=600,
    )


# --- Sidebar filters ---
def apply_sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filtros Globais")

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
        "Ano de protocolo",
        min_value=min_year, max_value=max_year,
        value=(min_year, max_year),
    )

    all_states = sorted(df["origem_valida"].dropna().unique())
    states = st.sidebar.multiselect(
        "Estado de origem",
        options=all_states,
        default=[],
        help="Vazio = todos os estados",
    )

    mask = (
        df["classe"].isin(classes)
        & df["status_processo"].isin(status)
        & df["ano"].between(year_range[0], year_range[1])
    )
    if states:
        mask = mask & df["origem_valida"].isin(states)

    return df[mask]


# --- Main ---
def main():
    CSV_PATH = "ArquivosConcatenados_1.csv"

    if not os.path.exists(CSV_PATH):
        st.error(f"Arquivo `{CSV_PATH}` não encontrado. Coloque-o na raiz do projeto.")
        return

    df_raw = load_data(CSV_PATH)
    vs_raw = load_virtual_sessions(CSV_PATH)
    dest_raw = load_destaques(CSV_PATH)
    vr_raw = load_votos_reajustados(CSV_PATH)
    vt_raw = load_vistas(CSV_PATH)
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
        "🖥️ Sessões Virtuais",
        "👁️ Pedidos de Vista",
        "🔄 Votos Reajustados",
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
        render_virtual_sessions(vs_raw, dest_raw, df)
    with tabs[7]:
        render_vistas(vt_raw, df)
    with tabs[8]:
        render_votos_reajustados(vr_raw, df)
    with tabs[9]:
        render_explorer(df)


if __name__ == "__main__":
    main()
