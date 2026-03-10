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

INCIDENT_TYPE_COLORS = {
    "Principal (PR)": "#2563eb",
    "Questões Incidentais (IJ)": "#7c3aed",
    "Recurso (RC)": "#d97706",
}

INCIDENT_SUBTYPE_COLORS = {
    "Mérito": "#2563eb",
    "MC": "#7c3aed",
    "MC-Ref": "#9333ea",
    "TPI": "#0891b2",
    "TPI-Ref": "#06b6d4",
    "AgR": "#d97706",
    "ED": "#dc2626",
    "AgR-ED": "#f97316",
    "ED-AgR": "#ea580c",
}

RESULT_COLORS = {
    "Unanimidade": "#16a34a",
    "Maioria (vencedor o relator)": "#2563eb",
    "Maioria (vencido o relator)": "#dc2626",
    "Sem resultado (destaque)": "#d97706",
    "Sem resultado (vista)": "#9333ea",
    "Não identificado": "#6b7280",
}

MODALIDADE_COLORS = {
    "Só presencial": "#0891b2",
    "Só virtual": "#7c3aed",
    "Misto (virtual e presencial)": "#d97706",
    "Só monocrática (sem julgamento colegiado)": "#6b7280",
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
_RE_INCIDENTE_VIRTUAL = re.compile(
    r"Julgamento Virtual:\s*(.*?)(?:\.\s*Incluído|\s*Incluído"
    r"|\.\s*-\s*Agendado|\s*-\s*Agendado|\s*$)"
)


def _parse_date(s: str):
    try:
        return pd.to_datetime(s, format="%d/%m/%Y")
    except Exception:
        return pd.NaT


def _classify_incident(raw: str) -> tuple[str, str]:
    """Classify a virtual-session incident per STF's 3-type taxonomy.

    Returns (tipo_incidente, subtipo_incidente).
    tipo: Principal (PR), Questões Incidentais (IJ), Recurso (RC).
    """
    upper = raw.upper()

    has_agr = "AGR" in upper
    ed_match = re.search(r'(?:^|[\s\-./])ED(?:[\s\-./]|$)', upper)
    has_ed = ed_match is not None

    if has_agr and has_ed:
        agr_pos = upper.index("AGR")
        ed_pos = ed_match.start()
        subtipo = "AgR-ED" if agr_pos < ed_pos else "ED-AgR"
        return ("Recurso (RC)", subtipo)
    if has_agr:
        return ("Recurso (RC)", "AgR")
    if has_ed:
        return ("Recurso (RC)", "ED")

    if "TPI" in upper:
        return ("Questões Incidentais (IJ)", "TPI-Ref" if "REF" in upper else "TPI")
    if "MC" in upper:
        return ("Questões Incidentais (IJ)", "MC-Ref" if "REF" in upper else "MC")

    return ("Principal (PR)", "Mérito")


_SESSION_DESTAQUE_NAMES = {
    "Retirado do Julgamento Virtual",
    "Processo destacado no Julgamento Virtual",
}

_SESSION_VISTA_NAMES = {
    "Vista ao(à) Ministro(a)",
    "VISTA AO MINISTRO",
    "VISTA À MINISTRA",
    "Vista",
    "VISTA",
}


def _determine_session_result(
    andamentos: list[dict],
    dt_inicio,
    dt_fim,
) -> str:
    """Determine the voting result of a virtual session.

    Categories:
      - Unanimidade
      - Maioria (vencedor o relator)
      - Maioria (vencido o relator)
      - Sem resultado (destaque)
      - Sem resultado (vista)
      - Não identificado
    """
    if pd.isna(dt_inicio):
        return "Não identificado"

    end_bound = (
        dt_fim + pd.Timedelta(days=7)
        if pd.notna(dt_fim)
        else dt_inicio + pd.Timedelta(days=30)
    )

    has_destaque = False
    has_vista = False
    best_result = ""

    for a in andamentos:
        data_str = a.get("data", "")
        try:
            a_dt = pd.to_datetime(data_str, format="%d/%m/%Y")
        except Exception:
            continue

        if a_dt < dt_inicio or a_dt > end_bound:
            continue

        nome = a.get("nome", "")
        comp = a.get("complemento", "")

        if nome in _SESSION_DESTAQUE_NAMES:
            has_destaque = True

        if nome in _SESSION_VISTA_NAMES or (
            nome == "Suspenso o julgamento" and "vista" in comp.lower()
        ):
            has_vista = True

        full = (nome + " " + comp).lower()
        if "unanimidade" in full or "unânime" in full:
            best_result = "unanimidade"
        elif "maioria" in full and best_result != "unanimidade":
            if "vencido" in full and (
                "relator" in full or "relatora" in full
            ):
                best_result = "maioria_vencido"
            elif best_result != "maioria_vencido":
                best_result = "maioria"

    if has_destaque:
        return "Sem resultado (destaque)"
    if has_vista:
        return "Sem resultado (vista)"
    if best_result == "unanimidade":
        return "Unanimidade"
    if best_result == "maioria_vencido":
        return "Maioria (vencido o relator)"
    if best_result == "maioria":
        return "Maioria (vencedor o relator)"
    return "Não identificado"


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
            incidente_raw = ""
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
                        m_inc = _RE_INCIDENTE_VIRTUAL.search(inc_comp)
                        if m_inc:
                            incidente_raw = re.sub(
                                r"\s*-?\s*Agendado para:.*", "",
                                m_inc.group(1),
                            ).strip().rstrip(". ")
                        matched_inclusao = True
                        break
                else:
                    m_single = _RE_DATE_SINGLE.search(inc_comp)
                    if m_single and m_single.group(1) == start_date_str:
                        m_lista = _RE_LISTA.search(inc_comp)
                        lista = m_lista.group(1) if m_lista else None
                        m_inc = _RE_INCIDENTE_VIRTUAL.search(inc_comp)
                        if m_inc:
                            incidente_raw = re.sub(
                                r"\s*-?\s*Agendado para:.*", "",
                                m_inc.group(1),
                            ).strip().rstrip(". ")
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
                "incidente_raw": incidente_raw,
                "resultado_sessao": _determine_session_result(
                    andamentos, dt_inicio, dt_fim,
                ),
            })

    if not records:
        return pd.DataFrame(columns=[
            "processo", "classe", "relator",
            "sessao_inicio", "sessao_fim", "lista",
            "incidente_raw", "incidente_tipo", "incidente_subtipo",
            "resultado_sessao",
        ])

    vs = pd.DataFrame(records)
    vs["sessao_inicio"] = pd.to_datetime(vs["sessao_inicio"], errors="coerce")
    vs["sessao_fim"] = pd.to_datetime(vs["sessao_fim"], errors="coerce")
    vs["ano_sessao"] = vs["sessao_inicio"].dt.year
    vs["mes_sessao"] = vs["sessao_inicio"].dt.to_period("M").astype(str)
    vs["semestre"] = vs["sessao_inicio"].apply(
        lambda d: f"{d.year}-S1" if pd.notna(d) and d.month <= 6
        else (f"{d.year}-S2" if pd.notna(d) else None)
    )

    incidente_class = vs["incidente_raw"].apply(
        lambda x: _classify_incident(x) if x else ("Principal (PR)", "Mérito")
    )
    vs["incidente_tipo"] = incidente_class.apply(lambda x: x[0])
    vs["incidente_subtipo"] = incidente_class.apply(lambda x: x[1])

    vs["duracao_dias"] = (vs["sessao_fim"] - vs["sessao_inicio"]).dt.days
    vs["tipo_sessao"] = vs["duracao_dias"].apply(
        lambda d: "Ordinária (≥6 dias)" if pd.notna(d) and d >= 6
        else ("Extraordinária (<6 dias)" if pd.notna(d) else "Não identificada")
    )

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


def _normalize_minister_name(name: str) -> str:
    """Strip common prefixes so relator and julgador names can be compared."""
    s = re.sub(
        r'^(?:MIN\.?\s*|MINISTR[OA]\s+)',
        '', str(name).strip(), flags=re.IGNORECASE,
    )
    return s.strip().upper()


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
            "is_autodestaque", "tipo_autoria",
        ])

    dest = pd.DataFrame(records)
    dest["data_dt"] = pd.to_datetime(
        dest["data"], format="%d/%m/%Y", errors="coerce"
    )
    dest["ano"] = dest["data_dt"].dt.year

    dest.sort_values(["processo", "data_dt"], inplace=True)
    rounds = []
    for proc, grp in dest.groupby("processo", sort=False):
        dates = grp["data_dt"].dropna().sort_values()
        r = 1
        prev = pd.NaT
        for idx, dt in dates.items():
            if pd.notna(prev) and (dt - prev).days > 2:
                r += 1
            rounds.append((idx, r))
            prev = dt
        for idx in grp.index.difference(dates.index):
            rounds.append((idx, r))
    if rounds:
        round_s = pd.Series(
            {idx: rnd for idx, rnd in rounds}, name="rodada"
        )
        dest["rodada"] = round_s
    else:
        dest["rodada"] = 0

    dest["is_autodestaque"] = dest.apply(
        lambda r: (
            _normalize_minister_name(r["relator"])
            == _normalize_minister_name(r["ministro_destaque"])
        )
        if r["ministro_destaque"] not in ("NA", "")
        else False,
        axis=1,
    )
    dest["tipo_autoria"] = dest.apply(
        lambda r: "Autodestaque (relator)"
        if r["is_autodestaque"]
        else (
            "Destaque por outro ministro"
            if r["ministro_destaque"] not in ("NA", "")
            else "Ministro não identificado"
        ),
        axis=1,
    )

    return dest


_DESTAQUE_PULL_NAMES = {
    "Retirado do Julgamento Virtual",
    "Processo destacado no Julgamento Virtual",
}


@st.cache_data(show_spinner="Identificando cancelamentos de destaque...")
def load_destaque_cancelamentos(path: str) -> pd.DataFrame:
    """Identify both formal and informal destaque cancellations.

    Formal: andamento 'Pedido de destaque cancelado' (from late 2022).
    Informal: destaque followed by return to virtual session with no vista
    in between.
    """
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

        events = []
        for a in andamentos:
            nome = a.get("nome", "")
            comp = a.get("complemento", "")
            data_str = a.get("data", "")
            try:
                dt = pd.to_datetime(data_str, format="%d/%m/%Y")
            except Exception:
                dt = pd.NaT

            if nome in _DESTAQUE_PULL_NAMES:
                events.append(("destaque", dt, nome, comp))
            elif nome == "Iniciado Julgamento Virtual":
                events.append(("virtual_return", dt, nome, comp))
            elif "Inclua-se em pauta" in nome and "Virtual" in comp:
                events.append(("virtual_return", dt, nome, comp))
            elif "vista" in nome.lower():
                events.append(("vista", dt, nome, comp))
            elif nome == "Pedido de destaque cancelado":
                events.append(("formal_cancel", dt, nome, comp))

        events.sort(key=lambda x: x[1] if pd.notna(x[1]) else pd.Timestamp.max)

        for i, (etype, edt, ename, ecomp) in enumerate(events):
            if etype == "formal_cancel":
                records.append({
                    "processo": row["nome_processo"],
                    "classe": row["classe"],
                    "relator": row["relator"],
                    "data_destaque": edt,
                    "data_retorno": edt,
                    "gap_dias": 0,
                    "tipo_cancelamento": "Formal",
                })
                continue

            if etype != "destaque":
                continue

            has_vista = False
            found_return = False
            return_dt = pd.NaT
            for j in range(i + 1, len(events)):
                next_type = events[j][0]
                if next_type == "vista":
                    has_vista = True
                    break
                if next_type == "formal_cancel":
                    break
                if next_type == "virtual_return":
                    found_return = True
                    return_dt = events[j][1]
                    break

            if found_return and not has_vista:
                gap = (
                    (return_dt - edt).days
                    if pd.notna(edt) and pd.notna(return_dt)
                    else None
                )
                records.append({
                    "processo": row["nome_processo"],
                    "classe": row["classe"],
                    "relator": row["relator"],
                    "data_destaque": edt,
                    "data_retorno": return_dt,
                    "gap_dias": gap,
                    "tipo_cancelamento": "Informal",
                })

    if not records:
        return pd.DataFrame(columns=[
            "processo", "classe", "relator", "data_destaque",
            "data_retorno", "gap_dias", "tipo_cancelamento",
        ])

    dc = pd.DataFrame(records)
    dc["ano"] = dc["data_destaque"].dt.year
    dc["faixa_gap"] = pd.cut(
        dc["gap_dias"],
        bins=[-1, 0, 7, 30, 180, 365, 99999],
        labels=[
            "Mesmo dia", "1–7 dias", "8–30 dias",
            "1–6 meses", "6–12 meses", ">1 ano",
        ],
    )
    return dc


_REAJUSTE_TERMS = [
    "voto reajustado", "reajustou o voto", "reajuste de voto",
    "reajustou seu voto", "reajustou voto",
]


_RE_SESSAO_VIRTUAL_DEC = re.compile(
    r"[Ss]ess[ãa]o\s+[Vv]irtual.*?(\d{2}/\d{2}/\d{4})\s*a\s*(\d{2}/\d{2}/\d{4})",
    re.DOTALL,
)


@st.cache_data(show_spinner="Extraindo votos alterados das decisões...")
def load_votos_alterados(path: str) -> pd.DataFrame:
    raw = pd.read_csv(
        path,
        usecols=["nome_processo", "classe", "relator", "decisões"],
    )

    records = []
    for _, row in raw.iterrows():
        try:
            decisoes = json.loads(row["decisões"])
        except Exception:
            continue

        for d in decisoes:
            nome = d.get("nome", "")
            comp = d.get("complemento", "")
            text = (nome + " " + comp).lower()
            if not any(t in text for t in _REAJUSTE_TERMS):
                continue

            m_virtual = _RE_SESSAO_VIRTUAL_DEC.search(comp)
            if m_virtual:
                tipo_sessao = "Virtual"
                sessao_inicio = _parse_date(m_virtual.group(1))
                sessao_fim = _parse_date(m_virtual.group(2))
            else:
                tipo_sessao = "Presencial"
                sessao_inicio = pd.NaT
                sessao_fim = pd.NaT

            records.append({
                "processo": row["nome_processo"],
                "classe": row["classe"],
                "relator": row["relator"],
                "data": d.get("data", ""),
                "nome_decisao": nome,
                "julgador": d.get("julgador", "NA"),
                "complemento": comp[:800],
                "tipo_sessao_voto": tipo_sessao,
                "sessao_inicio": sessao_inicio,
                "sessao_fim": sessao_fim,
            })

    if not records:
        return pd.DataFrame(columns=[
            "processo", "classe", "relator", "data",
            "nome_decisao", "julgador", "complemento",
            "tipo_sessao_voto", "sessao_inicio", "sessao_fim",
        ])

    va = pd.DataFrame(records)
    va["data_dt"] = pd.to_datetime(va["data"], format="%d/%m/%Y", errors="coerce")
    va["ano"] = va["data_dt"].dt.year
    va["sessao_inicio"] = pd.to_datetime(va["sessao_inicio"], errors="coerce")
    va["sessao_fim"] = pd.to_datetime(va["sessao_fim"], errors="coerce")
    return va


def _enrich_votos_alterados(
    va: pd.DataFrame, vs: pd.DataFrame,
) -> pd.DataFrame:
    """Add incidente_tipo to votos alterados by joining with virtual-sessions."""
    if va.empty:
        va["incidente_tipo"] = pd.Series(dtype=str)
        return va

    va = va.copy()

    if vs.empty or "sessao_inicio" not in vs.columns:
        va["incidente_tipo"] = "Não identificado"
        return va

    vs_key = (
        vs[["processo", "sessao_inicio", "incidente_tipo"]]
        .drop_duplicates(subset=["processo", "sessao_inicio"])
    )

    merged = va.merge(
        vs_key,
        on=["processo", "sessao_inicio"],
        how="left",
        suffixes=("", "_vs"),
    )
    merged["incidente_tipo"] = merged["incidente_tipo"].fillna("Não identificado")
    return merged


@st.cache_data(show_spinner="Classificando modalidade de julgamento dos processos...")
def load_case_venue(path: str) -> pd.DataFrame:
    """Classify each case's collegial judgment venue: virtual, presencial, or mixed."""
    raw = pd.read_csv(
        path,
        usecols=["nome_processo", "decisões"],
    )

    records = []
    for _, row in raw.iterrows():
        try:
            decisoes = json.loads(row["decisões"])
        except Exception:
            decisoes = []

        n_virtual = 0
        n_presencial = 0

        for d in decisoes:
            julgador = d.get("julgador", "")
            comp = d.get("complemento", "")
            full = (julgador + " " + comp).lower()

            is_collegial = any(
                t in full
                for t in (
                    "tribunal pleno", "plenário", "turma",
                    "sessão virtual",
                )
            )
            if not is_collegial:
                continue

            if "sessão virtual" in full:
                n_virtual += 1
            else:
                n_presencial += 1

        records.append({
            "processo": row["nome_processo"],
            "n_decisoes_virtual": n_virtual,
            "n_decisoes_presencial": n_presencial,
        })

    if not records:
        return pd.DataFrame(columns=[
            "processo", "n_decisoes_virtual", "n_decisoes_presencial",
            "modalidade",
        ])

    venue = pd.DataFrame(records)

    def _classify_venue(r):
        if r["n_decisoes_virtual"] > 0 and r["n_decisoes_presencial"] > 0:
            return "Misto (virtual e presencial)"
        if r["n_decisoes_virtual"] > 0:
            return "Só virtual"
        if r["n_decisoes_presencial"] > 0:
            return "Só presencial"
        return "Só monocrática (sem julgamento colegiado)"

    venue["modalidade"] = venue.apply(_classify_venue, axis=1)
    return venue


def render_virtual_sessions(vs: pd.DataFrame, df_main: pd.DataFrame):
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

    # --- Tipo de Sessão: Ordinária vs Extraordinária ---
    st.subheader("Tipo de Sessão: Ordinária vs Extraordinária")
    st.caption(
        "Classificação baseada na duração: sessões com ≥6 dias são consideradas "
        "ordinárias; sessões com <6 dias (tipicamente 1 dia) são extraordinárias."
    )

    ts1, ts2 = st.columns(2)
    with ts1:
        tipo_sessao_df = vs_f["tipo_sessao"].value_counts().reset_index()
        tipo_sessao_df.columns = ["Tipo", "Inclusões"]
        fig = px.pie(
            tipo_sessao_df, names="Tipo", values="Inclusões",
            title="Inclusões por Tipo de Sessão",
            hole=0.4,
            color="Tipo",
            color_discrete_map={
                "Ordinária (≥6 dias)": "#2563eb",
                "Extraordinária (<6 dias)": "#d97706",
                "Não identificada": "#6b7280",
            },
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with ts2:
        ts_year = (
            vs_f.dropna(subset=["ano_sessao"])
            .groupby(["ano_sessao", "tipo_sessao"])
            .size()
            .reset_index(name="inclusoes")
        )
        ts_year["ano_sessao"] = ts_year["ano_sessao"].astype(int)
        fig = px.bar(
            ts_year, x="ano_sessao", y="inclusoes", color="tipo_sessao",
            title="Tipo de Sessão por Ano",
            color_discrete_map={
                "Ordinária (≥6 dias)": "#2563eb",
                "Extraordinária (<6 dias)": "#d97706",
                "Não identificada": "#6b7280",
            },
            labels={
                "ano_sessao": "Ano", "inclusoes": "Inclusões",
                "tipo_sessao": "Tipo de Sessão",
            },
            text_auto=True,
        )
        fig.update_layout(barmode="stack", xaxis_dtick=1)
        st.plotly_chart(fig, use_container_width=True)

    ts_sem = (
        vs_f.dropna(subset=["semestre"])
        .groupby(["semestre", "tipo_sessao"])
        .size()
        .reset_index(name="inclusoes")
    )
    fig = px.bar(
        ts_sem, x="semestre", y="inclusoes", color="tipo_sessao",
        title="Tipo de Sessão por Semestre",
        color_discrete_map={
            "Ordinária (≥6 dias)": "#2563eb",
            "Extraordinária (<6 dias)": "#d97706",
            "Não identificada": "#6b7280",
        },
        labels={
            "semestre": "Semestre", "inclusoes": "Inclusões",
            "tipo_sessao": "Tipo de Sessão",
        },
    )
    fig.update_layout(barmode="stack", xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # --- Inclusões por Ano ---
    yearly_inc = (
        vs_f.dropna(subset=["ano_sessao"])
        .groupby(["ano_sessao", "classe"])
        .size()
        .reset_index(name="processos")
    )
    yearly_inc["ano_sessao"] = yearly_inc["ano_sessao"].astype(int)
    fig = px.bar(
        yearly_inc, x="ano_sessao", y="processos", color="classe",
        title="Processos Incluídos em Sessões Virtuais por Ano",
        color_discrete_map=COLORS,
        labels={"ano_sessao": "Ano", "processos": "Processos", "classe": "Classe"},
        text_auto=True,
    )
    fig.update_layout(barmode="stack", xaxis_dtick=1)
    st.plotly_chart(fig, use_container_width=True)

    # --- Inclusões por Semestre ---
    sem_inc = (
        vs_f.dropna(subset=["semestre"])
        .groupby(["semestre", "classe"])
        .size()
        .reset_index(name="processos")
    )
    fig = px.bar(
        sem_inc, x="semestre", y="processos", color="classe",
        title="Processos Incluídos em Sessões Virtuais por Semestre",
        color_discrete_map=COLORS,
        labels={"semestre": "Semestre", "processos": "Processos", "classe": "Classe"},
    )
    fig.update_layout(barmode="stack", xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)

    with c1:
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

    # --- Tipo de Incidente (classificação STF) ---
    st.divider()
    st.subheader("Tipo de Incidente Julgado nas Sessões Virtuais")
    st.caption(
        "Classificação conforme taxonomia do STF: "
        "**Principal (PR)** = julgamento de mérito; "
        "**Questões Incidentais (IJ)** = MC, MC-Ref, TPI, TPI-Ref; "
        "**Recurso (RC)** = AgR, ED, AgR-ED, ED-AgR."
    )

    ki1, ki2, ki3 = st.columns(3)
    for col, tipo in zip(
        [ki1, ki2, ki3],
        ["Principal (PR)", "Questões Incidentais (IJ)", "Recurso (RC)"],
    ):
        count = int((vs_f["incidente_tipo"] == tipo).sum())
        col.metric(tipo, f"{count:,}")

    ci1, ci2 = st.columns(2)
    with ci1:
        inc_counts = vs_f["incidente_tipo"].value_counts().reset_index()
        inc_counts.columns = ["Tipo", "Inclusões"]
        fig = px.pie(
            inc_counts, names="Tipo", values="Inclusões",
            title="Incidentes por Tipo",
            hole=0.4,
            color="Tipo",
            color_discrete_map=INCIDENT_TYPE_COLORS,
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with ci2:
        sub_counts = vs_f["incidente_subtipo"].value_counts().reset_index()
        sub_counts.columns = ["Subtipo", "Inclusões"]
        fig = px.pie(
            sub_counts, names="Subtipo", values="Inclusões",
            title="Detalhamento por Subtipo",
            hole=0.4,
            color="Subtipo",
            color_discrete_map=INCIDENT_SUBTYPE_COLORS,
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    inc_year = (
        vs_f.dropna(subset=["ano_sessao"])
        .groupby(["ano_sessao", "incidente_tipo"])
        .size()
        .reset_index(name="inclusoes")
    )
    inc_year["ano_sessao"] = inc_year["ano_sessao"].astype(int)
    fig = px.bar(
        inc_year, x="ano_sessao", y="inclusoes", color="incidente_tipo",
        title="Tipo de Incidente por Ano",
        color_discrete_map=INCIDENT_TYPE_COLORS,
        labels={
            "ano_sessao": "Ano", "inclusoes": "Inclusões",
            "incidente_tipo": "Tipo de Incidente",
        },
        text_auto=True,
    )
    fig.update_layout(barmode="stack", xaxis_dtick=1)
    st.plotly_chart(fig, use_container_width=True)

    sub_year = (
        vs_f.dropna(subset=["ano_sessao"])
        .groupby(["ano_sessao", "incidente_subtipo"])
        .size()
        .reset_index(name="inclusoes")
    )
    sub_year["ano_sessao"] = sub_year["ano_sessao"].astype(int)
    fig = px.bar(
        sub_year, x="ano_sessao", y="inclusoes", color="incidente_subtipo",
        title="Subtipo de Incidente por Ano",
        color_discrete_map=INCIDENT_SUBTYPE_COLORS,
        labels={
            "ano_sessao": "Ano", "inclusoes": "Inclusões",
            "incidente_subtipo": "Subtipo",
        },
    )
    fig.update_layout(barmode="stack", xaxis_dtick=1)
    st.plotly_chart(fig, use_container_width=True)

    inc_sem = (
        vs_f.dropna(subset=["semestre"])
        .groupby(["semestre", "incidente_tipo"])
        .size()
        .reset_index(name="inclusoes")
    )
    fig = px.bar(
        inc_sem, x="semestre", y="inclusoes", color="incidente_tipo",
        title="Tipo de Incidente por Semestre",
        color_discrete_map=INCIDENT_TYPE_COLORS,
        labels={
            "semestre": "Semestre", "inclusoes": "Inclusões",
            "incidente_tipo": "Tipo de Incidente",
        },
    )
    fig.update_layout(barmode="stack", xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

    # --- Resultado da Sessão Virtual ---
    st.divider()
    st.subheader("Resultado das Sessões Virtuais")
    st.caption(
        "Classificação do desfecho de cada inclusão em sessão virtual: "
        "**Unanimidade**, **Maioria (vencedor o relator)**, "
        "**Maioria (vencido o relator)**, ou **Sem resultado** "
        "(quando houve pedido de destaque ou de vista antes da conclusão)."
    )

    rk1, rk2, rk3, rk4, rk5 = st.columns(5)
    for col, label in zip(
        [rk1, rk2, rk3, rk4, rk5],
        [
            "Unanimidade",
            "Maioria (vencedor o relator)",
            "Maioria (vencido o relator)",
            "Sem resultado (destaque)",
            "Sem resultado (vista)",
        ],
    ):
        count = int((vs_f["resultado_sessao"] == label).sum())
        col.metric(label, f"{count:,}")

    rc1, rc2 = st.columns(2)
    with rc1:
        res_counts = vs_f["resultado_sessao"].value_counts().reset_index()
        res_counts.columns = ["Resultado", "Inclusões"]
        fig = px.pie(
            res_counts, names="Resultado", values="Inclusões",
            title="Distribuição dos Resultados",
            hole=0.4,
            color="Resultado",
            color_discrete_map=RESULT_COLORS,
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with rc2:
        res_year = (
            vs_f.dropna(subset=["ano_sessao"])
            .groupby(["ano_sessao", "resultado_sessao"])
            .size()
            .reset_index(name="inclusoes")
        )
        res_year["ano_sessao"] = res_year["ano_sessao"].astype(int)
        fig = px.bar(
            res_year, x="ano_sessao", y="inclusoes", color="resultado_sessao",
            title="Resultado por Ano",
            color_discrete_map=RESULT_COLORS,
            labels={
                "ano_sessao": "Ano", "inclusoes": "Inclusões",
                "resultado_sessao": "Resultado",
            },
            text_auto=True,
        )
        fig.update_layout(barmode="stack", xaxis_dtick=1)
        st.plotly_chart(fig, use_container_width=True)

    # --- Resultado × Classe ---
    rc3, rc4 = st.columns(2)
    with rc3:
        res_classe = (
            vs_f.groupby(["classe", "resultado_sessao"])
            .size()
            .reset_index(name="inclusoes")
        )
        fig = px.bar(
            res_classe, x="classe", y="inclusoes", color="resultado_sessao",
            title="Resultado por Classe Processual",
            color_discrete_map=RESULT_COLORS,
            labels={
                "classe": "Classe", "inclusoes": "Inclusões",
                "resultado_sessao": "Resultado",
            },
            text_auto=True,
        )
        fig.update_layout(barmode="stack")
        st.plotly_chart(fig, use_container_width=True)

    with rc4:
        res_inc = (
            vs_f.groupby(["incidente_tipo", "resultado_sessao"])
            .size()
            .reset_index(name="inclusoes")
        )
        fig = px.bar(
            res_inc, x="incidente_tipo", y="inclusoes", color="resultado_sessao",
            title="Resultado por Tipo de Incidente",
            color_discrete_map=RESULT_COLORS,
            labels={
                "incidente_tipo": "Tipo de Incidente", "inclusoes": "Inclusões",
                "resultado_sessao": "Resultado",
            },
            text_auto=True,
        )
        fig.update_layout(barmode="stack")
        st.plotly_chart(fig, use_container_width=True)

    # --- Resultado × Classe × Incidente (percentage view) ---
    decided = vs_f[~vs_f["resultado_sessao"].isin(
        ["Não identificado", "Sem resultado (destaque)", "Sem resultado (vista)"]
    )]
    if not decided.empty:
        st.caption(
            "Proporção entre unanimidade e maioria (excluindo sessões sem "
            "resultado e não identificadas):"
        )
        rc5, rc6 = st.columns(2)
        with rc5:
            dec_classe = (
                decided.groupby(["classe", "resultado_sessao"])
                .size()
                .reset_index(name="inclusoes")
            )
            fig = px.bar(
                dec_classe, x="classe", y="inclusoes", color="resultado_sessao",
                title="Unanimidade vs Maioria por Classe",
                color_discrete_map=RESULT_COLORS,
                labels={
                    "classe": "Classe", "inclusoes": "Inclusões",
                    "resultado_sessao": "Resultado",
                },
                text_auto=True,
            )
            fig.update_layout(barmode="stack")
            st.plotly_chart(fig, use_container_width=True)

        with rc6:
            dec_inc = (
                decided.groupby(["incidente_tipo", "resultado_sessao"])
                .size()
                .reset_index(name="inclusoes")
            )
            fig = px.bar(
                dec_inc, x="incidente_tipo", y="inclusoes", color="resultado_sessao",
                title="Unanimidade vs Maioria por Tipo de Incidente",
                color_discrete_map=RESULT_COLORS,
                labels={
                    "incidente_tipo": "Tipo de Incidente",
                    "inclusoes": "Inclusões",
                    "resultado_sessao": "Resultado",
                },
                text_auto=True,
            )
            fig.update_layout(barmode="stack")
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # --- Top busiest sessions ---
    st.subheader("Sessões Virtuais com Maior Volume")
    top_sessions = (
        vs_f.dropna(subset=["sessao_inicio"])
        .groupby(["sessao_label", "sessao_inicio"])
        .agg(
            processos=("processo", "count"),
            classes=("classe", lambda x: ", ".join(sorted(x.unique()))),
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

    # --- Relator & Classe breakdown ---
    c3, c4 = st.columns(2)

    with c3:
        rel_vs = vs_f["relator"].value_counts().head(15).reset_index()
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

    # --- Detailed session explorer ---
    st.divider()
    st.subheader("Explorar Sessões")
    search_session = st.text_input(
        "Buscar por processo ou relator:", "", key="vs_search"
    )
    explorer = vs_f[[
        "processo", "classe", "relator", "sessao_label",
        "tipo_sessao", "lista", "incidente_tipo", "incidente_subtipo",
        "resultado_sessao",
    ]].rename(columns={
        "processo": "Processo",
        "classe": "Classe",
        "relator": "Relator",
        "sessao_label": "Sessão (Período)",
        "tipo_sessao": "Tipo Sessão",
        "lista": "Lista",
        "incidente_tipo": "Tipo Incidente",
        "incidente_subtipo": "Subtipo",
        "resultado_sessao": "Resultado",
    }).sort_values("Sessão (Período)", ascending=False)

    if search_session:
        mask = (
            explorer["Processo"].str.contains(search_session, case=False, na=False)
            | explorer["Relator"].str.contains(search_session, case=False, na=False)
        )
        explorer = explorer[mask]

    st.caption(f"{len(explorer):,} inclusões em sessões virtuais")
    st.dataframe(explorer, use_container_width=True, height=500)


def render_destaques(dest: pd.DataFrame, df_main: pd.DataFrame):
    st.header("Destaques – Retirada de Sessão Virtual para Plenário Físico")

    if dest.empty:
        st.warning("Nenhum destaque encontrado nos dados.")
        return

    filtered_processes = set(df_main["nome_processo"])
    dest_f = dest[dest["processo"].isin(filtered_processes)].copy()

    if dest_f.empty:
        st.info("Nenhum destaque encontrado nos processos filtrados.")
        return

    real_destaques = dest_f[
        dest_f["evento"].isin([
            "Destaque (retirado da virtual)",
            "Julgamento presencial pós-destaque",
            "Destaque cancelado",
        ])
    ]

    if real_destaques.empty:
        st.info("Nenhum evento de destaque nos processos filtrados.")
        return

    n_cases = real_destaques["processo"].nunique()
    n_rounds = real_destaques.groupby("processo")["rodada"].nunique().sum()
    cases_multi = real_destaques.groupby("processo")["rodada"].nunique()
    n_cases_multi = int((cases_multi > 1).sum())
    n_raw_events = len(real_destaques)

    st.subheader("Visão por Processo vs. por Rodada de Destaque")
    st.info(
        f"**{n_cases}** processos tiveram ao menos um destaque. "
        f"Porém, como um mesmo caso pode ser destacado mais de uma vez "
        f"(ex.: inclusão de MC e depois de mérito), há **{int(n_rounds)} rodadas "
        f"distintas** de destaque ({n_raw_events} eventos brutos). "
        f"**{n_cases_multi}** processos possuem múltiplas rodadas. "
        f"Eventos com ≤2 dias de intervalo são agrupados na mesma rodada."
    )

    dc1, dc2, dc3, dc4 = st.columns(4)
    dc1.metric("Processos c/ Destaque", f"{n_cases:,}")
    dc2.metric("Rodadas de Destaque", f"{int(n_rounds):,}")
    dc3.metric("Processos c/ Múltiplas Rodadas", f"{n_cases_multi:,}")
    dc4.metric("Eventos Brutos", f"{n_raw_events:,}")

    n_pulled = real_destaques[
        real_destaques["evento"] == "Destaque (retirado da virtual)"
    ]["processo"].nunique()
    n_cancelled = real_destaques[
        real_destaques["evento"] == "Destaque cancelado"
    ]["processo"].nunique()
    n_physical = real_destaques[
        real_destaques["evento"] == "Julgamento presencial pós-destaque"
    ]["processo"].nunique()

    dc5, dc6, dc7 = st.columns(3)
    dc5.metric("Retirados da Virtual", f"{n_pulled:,}")
    dc6.metric("Destaques Cancelados", f"{n_cancelled:,}")
    dc7.metric("Julgados no Presencial", f"{n_physical:,}")

    # --- Autodestaque analysis ---
    pull_events = real_destaques[
        real_destaques["evento"] == "Destaque (retirado da virtual)"
    ]
    n_auto = int(pull_events["is_autodestaque"].sum())
    n_outro = int(
        ((~pull_events["is_autodestaque"])
         & (pull_events["ministro_destaque"] != "NA")).sum()
    )
    n_nao_id = int((pull_events["ministro_destaque"] == "NA").sum())

    st.divider()
    st.subheader("Autodestaque – Relator vs Outro Ministro")
    st.caption(
        "**Autodestaque**: o próprio relator do processo solicita a retirada "
        "da sessão virtual. Quando outro ministro solicita, trata-se de destaque "
        "por ministro diverso do relator."
    )

    da1, da2, da3 = st.columns(3)
    da1.metric("Autodestaques (relator)", f"{n_auto:,}")
    da2.metric("Destaque por Outro Ministro", f"{n_outro:,}")
    da3.metric("Ministro Não Identificado", f"{n_nao_id:,}")

    AUTORIA_COLORS = {
        "Autodestaque (relator)": "#d97706",
        "Destaque por outro ministro": "#2563eb",
        "Ministro não identificado": "#6b7280",
    }

    da4, da5 = st.columns(2)
    with da4:
        autoria_df = (
            pull_events["tipo_autoria"].value_counts().reset_index()
        )
        autoria_df.columns = ["Autoria", "Destaques"]
        fig = px.pie(
            autoria_df, names="Autoria", values="Destaques",
            title="Quem Solicita o Destaque?",
            hole=0.4,
            color="Autoria",
            color_discrete_map=AUTORIA_COLORS,
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with da5:
        autoria_year = (
            pull_events.dropna(subset=["ano"])
            .groupby(["ano", "tipo_autoria"])
            .size()
            .reset_index(name="destaques")
        )
        if not autoria_year.empty:
            autoria_year["ano"] = autoria_year["ano"].astype(int)
            fig = px.bar(
                autoria_year, x="ano", y="destaques", color="tipo_autoria",
                title="Autodestaque vs Outro Ministro por Ano",
                color_discrete_map=AUTORIA_COLORS,
                labels={
                    "ano": "Ano", "destaques": "Destaques",
                    "tipo_autoria": "Autoria",
                },
                text_auto=True,
            )
            fig.update_layout(barmode="stack", xaxis_dtick=1)
            st.plotly_chart(fig, use_container_width=True)

    # --- Top ministers requesting destaques, split by auto/other ---
    known = pull_events[pull_events["ministro_destaque"] != "NA"]
    if not known.empty:
        min_autoria = (
            known.groupby(["ministro_destaque", "tipo_autoria"])
            .size()
            .reset_index(name="destaques")
        )
        fig = px.bar(
            min_autoria, x="destaques", y="ministro_destaque",
            color="tipo_autoria", orientation="h",
            title="Ministros que Solicitam Destaque (autodestaque vs outro)",
            color_discrete_map=AUTORIA_COLORS,
            labels={
                "ministro_destaque": "Ministro",
                "destaques": "Destaques",
                "tipo_autoria": "Autoria",
            },
        )
        fig.update_layout(
            yaxis=dict(categoryorder="total ascending"),
            barmode="stack",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

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
                title="Ministros em Eventos de Destaque (todos os tipos)",
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

    # --- Distribution: rounds per case ---
    st.divider()
    st.subheader("Rodadas de Destaque por Processo")

    rounds_per_case = (
        real_destaques.groupby(["processo", "classe"])["rodada"]
        .nunique()
        .reset_index(name="rodadas")
    )
    dist_df = (
        rounds_per_case.groupby(["rodadas", "classe"])
        .size()
        .reset_index(name="processos")
    )
    dist_df["rodadas"] = dist_df["rodadas"].astype(str) + " rodada(s)"

    fig = px.bar(
        dist_df, x="rodadas", y="processos", color="classe",
        title="Quantos processos tiveram 1, 2, 3… rodadas de destaque",
        color_discrete_map=COLORS,
        labels={"rodadas": "Nº de Rodadas", "processos": "Processos", "classe": "Classe"},
        text_auto=True,
    )
    fig.update_layout(barmode="stack")
    st.plotly_chart(fig, use_container_width=True)

    # --- Table: processes with multiple rounds ---
    if n_cases_multi > 0:
        with st.expander(f"Processos com múltiplas rodadas ({n_cases_multi})"):
            multi_rounds = (
                rounds_per_case[rounds_per_case["rodadas"] > 1]
                .merge(
                    real_destaques[["processo", "relator"]].drop_duplicates(),
                    on="processo",
                )
                .sort_values("rodadas", ascending=False)
                .rename(columns={
                    "processo": "Processo",
                    "classe": "Classe",
                    "relator": "Relator",
                    "rodadas": "Rodadas",
                })
            )
            st.dataframe(multi_rounds, use_container_width=True, height=300)

    st.divider()
    st.subheader("Tabela de Destaques")
    dest_display = real_destaques[[
        "processo", "classe", "relator", "data", "rodada", "evento",
        "ministro_destaque", "tipo_autoria", "sessao_destaque",
    ]].rename(columns={
        "processo": "Processo",
        "classe": "Classe",
        "relator": "Relator",
        "data": "Data",
        "rodada": "Rodada",
        "evento": "Evento",
        "ministro_destaque": "Min. Destaque",
        "tipo_autoria": "Autoria",
        "sessao_destaque": "Sessão Virtual",
    }).sort_values(["Processo", "Data"], ascending=[True, False])
    st.dataframe(dest_display, use_container_width=True, height=400)


def render_cancelamentos(dc: pd.DataFrame, df_main: pd.DataFrame):
    st.header("Cancelamentos de Destaque – Formal e Informal")
    st.caption(
        "**Formal**: andamento 'Pedido de destaque cancelado' (a partir de nov/2022). "
        "**Informal**: caso destacado que retorna à sessão virtual sem vista "
        "intermediária — prática identificada desde dez/2017."
    )

    if dc.empty:
        st.warning("Nenhum cancelamento de destaque encontrado.")
        return

    filtered_processes = set(df_main["nome_processo"])
    dc_f = dc[dc["processo"].isin(filtered_processes)].copy()

    if dc_f.empty:
        st.info("Nenhum cancelamento nos processos filtrados.")
        return

    n_total = len(dc_f)
    n_formal = len(dc_f[dc_f["tipo_cancelamento"] == "Formal"])
    n_informal = len(dc_f[dc_f["tipo_cancelamento"] == "Informal"])
    n_cases = dc_f["processo"].nunique()
    median_gap = dc_f.loc[dc_f["tipo_cancelamento"] == "Informal", "gap_dias"].median()

    kc1, kc2, kc3, kc4, kc5 = st.columns(5)
    kc1.metric("Total de Cancelamentos", f"{n_total:,}")
    kc2.metric("Formais", f"{n_formal:,}")
    kc3.metric("Informais", f"{n_informal:,}")
    kc4.metric("Processos Envolvidos", f"{n_cases:,}")
    kc5.metric("Mediana do Gap (informal)", f"{int(median_gap)} dias" if pd.notna(median_gap) else "—")

    st.divider()

    # --- Formal vs Informal pie ---
    cc1, cc2 = st.columns(2)
    with cc1:
        tipo_df = dc_f["tipo_cancelamento"].value_counts().reset_index()
        tipo_df.columns = ["Tipo", "Cancelamentos"]
        fig = px.pie(
            tipo_df, names="Tipo", values="Cancelamentos",
            title="Cancelamentos: Formal vs Informal",
            hole=0.4,
            color="Tipo",
            color_discrete_map={
                "Formal": "#2563eb",
                "Informal": "#d97706",
            },
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with cc2:
        # --- By year, stacked formal/informal ---
        yr_df = (
            dc_f.dropna(subset=["ano"])
            .groupby(["ano", "tipo_cancelamento"])
            .size()
            .reset_index(name="cancelamentos")
        )
        yr_df["ano"] = yr_df["ano"].astype(int)
        fig = px.bar(
            yr_df, x="ano", y="cancelamentos", color="tipo_cancelamento",
            title="Cancelamentos de Destaque por Ano",
            color_discrete_map={
                "Formal": "#2563eb",
                "Informal": "#d97706",
            },
            labels={
                "ano": "Ano", "cancelamentos": "Cancelamentos",
                "tipo_cancelamento": "Tipo",
            },
            text_auto=True,
        )
        fig.update_layout(barmode="stack", xaxis_dtick=1)
        st.plotly_chart(fig, use_container_width=True)

    # --- Gap analysis (informal only) ---
    informal = dc_f[dc_f["tipo_cancelamento"] == "Informal"]
    if not informal.empty:
        st.divider()
        st.subheader("Análise do Intervalo – Cancelamentos Informais")
        st.caption(
            "Dias entre o destaque e o retorno à sessão virtual. "
            "Gap = 0 indica cancelamento imediato (mesmo dia)."
        )

        gc1, gc2 = st.columns(2)
        with gc1:
            faixa_df = (
                informal["faixa_gap"]
                .value_counts()
                .reindex([
                    "Mesmo dia", "1–7 dias", "8–30 dias",
                    "1–6 meses", "6–12 meses", ">1 ano",
                ])
                .dropna()
                .reset_index()
            )
            faixa_df.columns = ["Faixa", "Casos"]
            fig = px.bar(
                faixa_df, x="Faixa", y="Casos",
                title="Distribuição do Intervalo (destaque → retorno à virtual)",
                text_auto=True,
                color="Faixa",
                color_discrete_sequence=px.colors.sequential.YlOrRd,
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        with gc2:
            fig = px.histogram(
                informal, x="gap_dias",
                title="Histograma: Dias entre Destaque e Retorno",
                nbins=40,
                labels={"gap_dias": "Dias", "count": "Ocorrências"},
            )
            fig.update_traces(marker_color="#d97706")
            st.plotly_chart(fig, use_container_width=True)

        # --- Same-day vs delayed, by year ---
        informal_cat = informal.copy()
        informal_cat["categoria"] = informal_cat["gap_dias"].apply(
            lambda d: "Mesmo dia (imediato)" if d == 0
            else ("≤30 dias" if d <= 30 else ">30 dias")
        )
        cat_year = (
            informal_cat.dropna(subset=["ano"])
            .groupby(["ano", "categoria"])
            .size()
            .reset_index(name="casos")
        )
        cat_year["ano"] = cat_year["ano"].astype(int)
        fig = px.bar(
            cat_year, x="ano", y="casos", color="categoria",
            title="Cancelamentos Informais por Ano: Imediatos vs Atrasados",
            color_discrete_map={
                "Mesmo dia (imediato)": "#16a34a",
                "≤30 dias": "#d97706",
                ">30 dias": "#dc2626",
            },
            labels={
                "ano": "Ano", "casos": "Cancelamentos",
                "categoria": "Intervalo",
            },
            text_auto=True,
        )
        fig.update_layout(barmode="stack", xaxis_dtick=1)
        st.plotly_chart(fig, use_container_width=True)

    # --- By class ---
    st.divider()
    cc3, cc4 = st.columns(2)
    with cc3:
        cls_df = (
            dc_f.groupby(["classe", "tipo_cancelamento"])
            .size()
            .reset_index(name="cancelamentos")
        )
        fig = px.bar(
            cls_df, x="classe", y="cancelamentos", color="tipo_cancelamento",
            title="Cancelamentos por Classe",
            color_discrete_map={
                "Formal": "#2563eb",
                "Informal": "#d97706",
            },
            labels={
                "classe": "Classe", "cancelamentos": "Cancelamentos",
                "tipo_cancelamento": "Tipo",
            },
            text_auto=True,
        )
        fig.update_layout(barmode="stack")
        st.plotly_chart(fig, use_container_width=True)

    with cc4:
        rel_df = (
            dc_f["relator"]
            .value_counts()
            .head(15)
            .reset_index()
        )
        rel_df.columns = ["Relator", "Cancelamentos"]
        fig = px.bar(
            rel_df, x="Cancelamentos", y="Relator", orientation="h",
            title="Top 15 Relatores com Cancelamento de Destaque",
            color="Cancelamentos", color_continuous_scale="OrRd",
        )
        fig.update_layout(yaxis=dict(categoryorder="total ascending"))
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    # --- Explorer table ---
    st.divider()
    st.subheader("Tabela de Cancelamentos")
    show_df = dc_f[[
        "processo", "classe", "relator", "tipo_cancelamento",
        "data_destaque", "data_retorno", "gap_dias", "faixa_gap",
    ]].rename(columns={
        "processo": "Processo",
        "classe": "Classe",
        "relator": "Relator",
        "tipo_cancelamento": "Tipo",
        "data_destaque": "Data Destaque",
        "data_retorno": "Data Retorno",
        "gap_dias": "Gap (dias)",
        "faixa_gap": "Faixa",
    }).sort_values("Data Destaque", ascending=True)
    st.dataframe(show_df, use_container_width=True, height=500)


SESSAO_VOTO_COLORS = {
    "Virtual": "#7c3aed",
    "Presencial": "#0891b2",
}


def render_votos_alterados(
    va: pd.DataFrame, vs: pd.DataFrame, df_main: pd.DataFrame,
):
    st.header("Votos Alterados (Reajustados) – Decisões")

    if va.empty:
        st.warning("Nenhum voto alterado encontrado nas decisões.")
        return

    filtered_processes = set(df_main["nome_processo"])
    va_f = _enrich_votos_alterados(
        va[va["processo"].isin(filtered_processes)].copy(), vs,
    )

    if va_f.empty:
        st.info("Nenhum voto alterado nos processos filtrados.")
        return

    # ---- KPIs ----
    n_occurrences = len(va_f)
    n_cases = va_f["processo"].nunique()
    n_virtual = int((va_f["tipo_sessao_voto"] == "Virtual").sum())
    n_presencial = int((va_f["tipo_sessao_voto"] == "Presencial").sum())
    pct_cases = n_cases / len(df_main) * 100 if len(df_main) > 0 else 0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Ocorrências de Voto Alterado", f"{n_occurrences:,}")
    k2.metric("Processos com Voto Alterado", f"{n_cases:,}")
    k3.metric("% dos Processos", f"{pct_cases:.2f}%")
    k4.metric("Em Sessão Virtual", f"{n_virtual:,}")
    k5.metric("Em Sessão Presencial", f"{n_presencial:,}")

    st.divider()

    # ---- Virtual vs Presencial ----
    st.subheader("Sessão Virtual vs Presencial")

    vp1, vp2 = st.columns(2)
    with vp1:
        sessao_df = va_f["tipo_sessao_voto"].value_counts().reset_index()
        sessao_df.columns = ["Tipo de Sessão", "Ocorrências"]
        fig = px.pie(
            sessao_df, names="Tipo de Sessão", values="Ocorrências",
            title="Votos Alterados: Virtual vs Presencial",
            hole=0.4,
            color="Tipo de Sessão",
            color_discrete_map=SESSAO_VOTO_COLORS,
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with vp2:
        sessao_year = (
            va_f.dropna(subset=["ano"])
            .groupby(["ano", "tipo_sessao_voto"])
            .size()
            .reset_index(name="ocorrencias")
        )
        if not sessao_year.empty:
            sessao_year["ano"] = sessao_year["ano"].astype(int)
            fig = px.bar(
                sessao_year, x="ano", y="ocorrencias", color="tipo_sessao_voto",
                title="Votos Alterados por Ano (Virtual vs Presencial)",
                color_discrete_map=SESSAO_VOTO_COLORS,
                labels={
                    "ano": "Ano", "ocorrencias": "Ocorrências",
                    "tipo_sessao_voto": "Tipo de Sessão",
                },
                text_auto=True,
            )
            fig.update_layout(barmode="stack", xaxis_dtick=1)
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ---- By Classe (case type) ----
    st.subheader("Por Classe Processual")

    cl1, cl2 = st.columns(2)
    with cl1:
        occ_classe = va_f["classe"].value_counts().reset_index()
        occ_classe.columns = ["Classe", "Ocorrências"]
        fig = px.bar(
            occ_classe, x="Classe", y="Ocorrências",
            title="Ocorrências de Voto Alterado por Classe",
            color="Classe", color_discrete_map=COLORS,
            text_auto=True,
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with cl2:
        cases_classe = (
            va_f.drop_duplicates(subset=["processo"])["classe"]
            .value_counts()
            .reset_index()
        )
        cases_classe.columns = ["Classe", "Processos"]
        fig = px.bar(
            cases_classe, x="Classe", y="Processos",
            title="Processos com Voto Alterado por Classe",
            color="Classe", color_discrete_map=COLORS,
            text_auto=True,
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    classe_sessao = (
        va_f.groupby(["classe", "tipo_sessao_voto"])
        .size()
        .reset_index(name="ocorrencias")
    )
    fig = px.bar(
        classe_sessao, x="classe", y="ocorrencias", color="tipo_sessao_voto",
        title="Virtual vs Presencial por Classe",
        color_discrete_map=SESSAO_VOTO_COLORS,
        labels={
            "classe": "Classe", "ocorrencias": "Ocorrências",
            "tipo_sessao_voto": "Tipo de Sessão",
        },
        text_auto=True,
    )
    fig.update_layout(barmode="stack")
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ---- By Tipo de Incidente ----
    st.subheader("Por Tipo de Incidente")
    st.caption(
        "O tipo de incidente é identificado por cruzamento com as sessões virtuais. "
        "Votos em sessões presenciais ou sem correspondência aparecem como "
        "'Não identificado'."
    )

    ti1, ti2 = st.columns(2)
    with ti1:
        occ_inc = va_f["incidente_tipo"].value_counts().reset_index()
        occ_inc.columns = ["Tipo de Incidente", "Ocorrências"]
        fig = px.pie(
            occ_inc, names="Tipo de Incidente", values="Ocorrências",
            title="Ocorrências por Tipo de Incidente",
            hole=0.4,
            color="Tipo de Incidente",
            color_discrete_map={**INCIDENT_TYPE_COLORS, "Não identificado": "#6b7280"},
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with ti2:
        cases_inc = (
            va_f.drop_duplicates(subset=["processo", "incidente_tipo"])
            .groupby("incidente_tipo")
            .size()
            .reset_index(name="processos")
        )
        cases_inc.columns = ["Tipo de Incidente", "Processos"]
        fig = px.bar(
            cases_inc, x="Tipo de Incidente", y="Processos",
            title="Processos com Voto Alterado por Tipo de Incidente",
            color="Tipo de Incidente",
            color_discrete_map={**INCIDENT_TYPE_COLORS, "Não identificado": "#6b7280"},
            text_auto=True,
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    inc_year = (
        va_f.dropna(subset=["ano"])
        .groupby(["ano", "incidente_tipo"])
        .size()
        .reset_index(name="ocorrencias")
    )
    if not inc_year.empty:
        inc_year["ano"] = inc_year["ano"].astype(int)
        fig = px.bar(
            inc_year, x="ano", y="ocorrencias", color="incidente_tipo",
            title="Votos Alterados por Ano e Tipo de Incidente",
            color_discrete_map={**INCIDENT_TYPE_COLORS, "Não identificado": "#6b7280"},
            labels={
                "ano": "Ano", "ocorrencias": "Ocorrências",
                "incidente_tipo": "Tipo de Incidente",
            },
            text_auto=True,
        )
        fig.update_layout(barmode="stack", xaxis_dtick=1)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ---- Classe × Incidente cross-tab ----
    st.subheader("Classe × Tipo de Incidente")
    cross = (
        va_f.groupby(["classe", "incidente_tipo"])
        .size()
        .reset_index(name="ocorrencias")
    )
    fig = px.bar(
        cross, x="classe", y="ocorrencias", color="incidente_tipo",
        title="Ocorrências: Classe × Tipo de Incidente",
        color_discrete_map={**INCIDENT_TYPE_COLORS, "Não identificado": "#6b7280"},
        labels={
            "classe": "Classe", "ocorrencias": "Ocorrências",
            "incidente_tipo": "Tipo de Incidente",
        },
        text_auto=True,
    )
    fig.update_layout(barmode="stack")
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ---- Relatores ----
    st.subheader("Relatores")
    rel_counts = va_f["relator"].value_counts().head(15).reset_index()
    rel_counts.columns = ["Relator", "Ocorrências"]
    fig = px.bar(
        rel_counts, x="Ocorrências", y="Relator", orientation="h",
        title="Top 15 Relatores com Votos Alterados",
        color="Ocorrências", color_continuous_scale="Teal",
    )
    fig.update_layout(yaxis=dict(categoryorder="total ascending"))
    fig.update_coloraxes(showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ---- Explorer table ----
    st.subheader("Detalhamento dos Votos Alterados")
    search_va = st.text_input(
        "Buscar por processo, relator ou texto:", "", key="va_search",
    )
    va_display = va_f[[
        "processo", "classe", "relator", "data", "nome_decisao",
        "julgador", "tipo_sessao_voto", "incidente_tipo", "complemento",
    ]].rename(columns={
        "processo": "Processo",
        "classe": "Classe",
        "relator": "Relator",
        "data": "Data",
        "nome_decisao": "Decisão",
        "julgador": "Órgão Julgador",
        "tipo_sessao_voto": "Tipo Sessão",
        "incidente_tipo": "Tipo Incidente",
        "complemento": "Texto",
    }).sort_values("Data", ascending=False)

    if search_va:
        mask = (
            va_display["Processo"].str.contains(search_va, case=False, na=False)
            | va_display["Relator"].str.contains(search_va, case=False, na=False)
            | va_display["Texto"].str.contains(search_va, case=False, na=False)
        )
        va_display = va_display[mask]

    st.caption(f"{len(va_display):,} ocorrências de votos alterados")
    st.dataframe(va_display, use_container_width=True, height=500)


def render_situacao_processos(
    venue: pd.DataFrame, vs: pd.DataFrame, df_main: pd.DataFrame,
):
    st.header("Situação dos Processos – Baixados e Modalidade de Julgamento")

    if df_main.empty:
        st.warning("Nenhum processo nos filtros atuais.")
        return

    # ---- merge venue into main df ----
    merged = df_main.merge(
        venue[["processo", "modalidade", "n_decisoes_virtual", "n_decisoes_presencial"]],
        left_on="nome_processo",
        right_on="processo",
        how="left",
    )
    merged["modalidade"] = merged["modalidade"].fillna("Só monocrática (sem julgamento colegiado)")

    # ---- primary incidente_tipo per case from VS data ----
    if not vs.empty:
        case_inc = (
            vs.groupby("processo")["incidente_tipo"]
            .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else "Não identificado")
            .reset_index()
            .rename(columns={"incidente_tipo": "incidente_principal"})
        )
        merged = merged.merge(
            case_inc, left_on="nome_processo", right_on="processo",
            how="left", suffixes=("", "_inc"),
        )
        merged["incidente_principal"] = merged["incidente_principal"].fillna("N/A")
    else:
        merged["incidente_principal"] = "N/A"

    # ================================================================
    # A) Baixados vs Em andamento
    # ================================================================
    st.subheader("Processos Baixados vs Em Andamento")

    n_total = len(merged)
    n_baixados = int((merged["status_processo"] == "Finalizado").sum())
    n_andamento = int((merged["status_processo"] == "Em andamento").sum())

    ka1, ka2, ka3 = st.columns(3)
    ka1.metric("Total de Processos", f"{n_total:,}")
    ka2.metric("Baixados (Finalizados)", f"{n_baixados:,}")
    ka3.metric("Em Andamento", f"{n_andamento:,}")

    sa1, sa2 = st.columns(2)
    with sa1:
        status_df = merged["status_processo"].value_counts().reset_index()
        status_df.columns = ["Status", "Processos"]
        fig = px.pie(
            status_df, names="Status", values="Processos",
            title="Situação dos Processos",
            hole=0.4,
            color="Status",
            color_discrete_map={"Finalizado": "#16a34a", "Em andamento": "#2563eb"},
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with sa2:
        status_year = (
            merged.dropna(subset=["ano"])
            .groupby(["ano", "status_processo"])
            .size()
            .reset_index(name="processos")
        )
        status_year["ano"] = status_year["ano"].astype(int)
        fig = px.bar(
            status_year, x="ano", y="processos", color="status_processo",
            title="Situação por Ano de Protocolo",
            color_discrete_map={"Finalizado": "#16a34a", "Em andamento": "#2563eb"},
            labels={
                "ano": "Ano", "processos": "Processos",
                "status_processo": "Status",
            },
        )
        fig.update_layout(barmode="stack", xaxis_dtick=2)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ================================================================
    # B) Modalidade de Julgamento nos Baixados
    # ================================================================
    st.subheader("Modalidade de Julgamento – Processos Baixados")
    st.caption(
        "Para os processos finalizados, classifica-se a modalidade com base nas "
        "decisões colegiadas (Tribunal Pleno / Turma): se todas mencionam "
        "'Sessão Virtual' → **Só virtual**; se nenhuma menciona → **Só presencial**; "
        "se há ambas → **Misto**."
    )

    baixados = merged[merged["status_processo"] == "Finalizado"]

    if baixados.empty:
        st.info("Nenhum processo baixado nos filtros atuais.")
        return

    n_virtual = int((baixados["modalidade"] == "Só virtual").sum())
    n_presencial = int((baixados["modalidade"] == "Só presencial").sum())
    n_misto = int((baixados["modalidade"] == "Misto (virtual e presencial)").sum())
    n_sem = int((baixados["modalidade"] == "Só monocrática (sem julgamento colegiado)").sum())

    kb1, kb2, kb3, kb4 = st.columns(4)
    kb1.metric("Só Presencial", f"{n_presencial:,}")
    kb2.metric("Só Virtual", f"{n_virtual:,}")
    kb3.metric("Misto", f"{n_misto:,}")
    kb4.metric("Só Monocrática", f"{n_sem:,}")

    sb1, sb2 = st.columns(2)
    with sb1:
        mod_df = baixados["modalidade"].value_counts().reset_index()
        mod_df.columns = ["Modalidade", "Processos"]
        fig = px.pie(
            mod_df, names="Modalidade", values="Processos",
            title="Modalidade de Julgamento (Baixados)",
            hole=0.4,
            color="Modalidade",
            color_discrete_map=MODALIDADE_COLORS,
        )
        fig.update_traces(textinfo="value+percent")
        st.plotly_chart(fig, use_container_width=True)

    with sb2:
        mod_year = (
            baixados.dropna(subset=["ano"])
            .groupby(["ano", "modalidade"])
            .size()
            .reset_index(name="processos")
        )
        mod_year["ano"] = mod_year["ano"].astype(int)
        fig = px.bar(
            mod_year, x="ano", y="processos", color="modalidade",
            title="Modalidade por Ano de Protocolo (Baixados)",
            color_discrete_map=MODALIDADE_COLORS,
            labels={
                "ano": "Ano", "processos": "Processos",
                "modalidade": "Modalidade",
            },
        )
        fig.update_layout(barmode="stack", xaxis_dtick=2)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ================================================================
    # C) Segmentação por Ano — visão detalhada
    # ================================================================
    st.subheader("Evolução Temporal")

    mod_year_full = (
        merged.dropna(subset=["ano"])
        .groupby(["ano", "status_processo", "modalidade"])
        .size()
        .reset_index(name="processos")
    )
    mod_year_full["ano"] = mod_year_full["ano"].astype(int)
    fig = px.bar(
        mod_year_full, x="ano", y="processos", color="modalidade",
        facet_row="status_processo",
        title="Modalidade por Ano – Baixados e Em Andamento",
        color_discrete_map=MODALIDADE_COLORS,
        labels={
            "ano": "Ano", "processos": "Processos",
            "modalidade": "Modalidade", "status_processo": "Status",
        },
    )
    fig.update_layout(barmode="stack", xaxis_dtick=2, height=600)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ================================================================
    # D) Segmentação por Classe e Tipo de Incidente
    # ================================================================
    st.subheader("Por Classe Processual")

    dc1, dc2 = st.columns(2)
    with dc1:
        cls_status = (
            merged.groupby(["classe", "status_processo"])
            .size()
            .reset_index(name="processos")
        )
        fig = px.bar(
            cls_status, x="classe", y="processos", color="status_processo",
            title="Baixados vs Em Andamento por Classe",
            color_discrete_map={"Finalizado": "#16a34a", "Em andamento": "#2563eb"},
            labels={
                "classe": "Classe", "processos": "Processos",
                "status_processo": "Status",
            },
            text_auto=True,
        )
        fig.update_layout(barmode="stack")
        st.plotly_chart(fig, use_container_width=True)

    with dc2:
        cls_mod = (
            baixados.groupby(["classe", "modalidade"])
            .size()
            .reset_index(name="processos")
        )
        fig = px.bar(
            cls_mod, x="classe", y="processos", color="modalidade",
            title="Modalidade de Julgamento por Classe (Baixados)",
            color_discrete_map=MODALIDADE_COLORS,
            labels={
                "classe": "Classe", "processos": "Processos",
                "modalidade": "Modalidade",
            },
            text_auto=True,
        )
        fig.update_layout(barmode="stack")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("Por Tipo de Incidente")
    st.caption(
        "O tipo de incidente principal de cada processo é determinado pela sessão "
        "virtual mais frequente (quando existente). Processos sem sessão virtual "
        "aparecem como 'N/A'."
    )

    di1, di2 = st.columns(2)
    with di1:
        inc_status = (
            merged.groupby(["incidente_principal", "status_processo"])
            .size()
            .reset_index(name="processos")
        )
        fig = px.bar(
            inc_status, x="incidente_principal", y="processos",
            color="status_processo",
            title="Baixados vs Em Andamento por Tipo de Incidente",
            color_discrete_map={"Finalizado": "#16a34a", "Em andamento": "#2563eb"},
            labels={
                "incidente_principal": "Tipo de Incidente",
                "processos": "Processos",
                "status_processo": "Status",
            },
            text_auto=True,
        )
        fig.update_layout(barmode="stack")
        st.plotly_chart(fig, use_container_width=True)

    with di2:
        baixados_inc = baixados[baixados["incidente_principal"] != "N/A"]
        if not baixados_inc.empty:
            inc_mod = (
                baixados_inc.groupby(["incidente_principal", "modalidade"])
                .size()
                .reset_index(name="processos")
            )
            fig = px.bar(
                inc_mod, x="incidente_principal", y="processos",
                color="modalidade",
                title="Modalidade por Tipo de Incidente (Baixados c/ Sessão Virtual)",
                color_discrete_map=MODALIDADE_COLORS,
                labels={
                    "incidente_principal": "Tipo de Incidente",
                    "processos": "Processos",
                    "modalidade": "Modalidade",
                },
                text_auto=True,
            )
            fig.update_layout(barmode="stack")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhum processo baixado com sessão virtual identificada.")

    # ---- Classe × Incidente × Modalidade ----
    st.divider()
    st.subheader("Classe × Tipo de Incidente (Baixados)")

    baixados_cross = baixados[baixados["incidente_principal"] != "N/A"]
    if not baixados_cross.empty:
        cross_df = (
            baixados_cross.groupby(["classe", "incidente_principal", "modalidade"])
            .size()
            .reset_index(name="processos")
        )
        fig = px.bar(
            cross_df, x="classe", y="processos", color="modalidade",
            facet_col="incidente_principal",
            title="Modalidade por Classe e Tipo de Incidente",
            color_discrete_map=MODALIDADE_COLORS,
            labels={
                "classe": "Classe", "processos": "Processos",
                "modalidade": "Modalidade",
                "incidente_principal": "Incidente",
            },
            text_auto=True,
        )
        fig.update_layout(barmode="stack")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ---- Explorer table ----
    st.subheader("Tabela de Processos")
    display_cols = [
        "nome_processo", "classe", "relator", "ano",
        "status_processo", "modalidade",
        "n_decisoes_virtual", "n_decisoes_presencial",
        "incidente_principal",
    ]
    renamed = {
        "nome_processo": "Processo",
        "classe": "Classe",
        "relator": "Relator",
        "ano": "Ano",
        "status_processo": "Status",
        "modalidade": "Modalidade",
        "n_decisoes_virtual": "Decisões Virtuais",
        "n_decisoes_presencial": "Decisões Presenciais",
        "incidente_principal": "Incidente Principal",
    }
    available = [c for c in display_cols if c in merged.columns]
    show = merged[available].rename(
        columns={k: v for k, v in renamed.items() if k in available}
    ).sort_values("Ano" if "Ano" in renamed.values() else available[0], ascending=False)
    st.caption(f"{len(show):,} processos")
    st.dataframe(show, use_container_width=True, height=500)


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
        max_and = int(df["len(andamentos_lista)"].max())
        bins = list(range(0, max_and + 11, 10))
        labels_and = [f"{b+1}–{b+10}" for b in bins[:-1]]
        labels_and[0] = "0–10"
        tmp = df[["len(andamentos_lista)", "classe"]].copy()
        tmp["faixa"] = pd.cut(
            tmp["len(andamentos_lista)"], bins=bins, labels=labels_and,
            include_lowest=True, right=True,
        )
        grouped = (
            tmp.groupby(["faixa", "classe"], observed=True)
            .size()
            .reset_index(name="processos")
        )
        fig = px.bar(
            grouped, x="faixa", y="processos", color="classe",
            title="Distribuição de Andamentos por Processo (faixas de 10)",
            color_discrete_map=COLORS,
            labels={"faixa": "Nº de Andamentos", "processos": "Processos", "classe": "Classe"},
        )
        fig.update_layout(barmode="stack", xaxis_tickangle=-45)
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
    CSV_PATH = "ArquivosConcatenados.csv"

    if not os.path.exists(CSV_PATH):
        st.error(f"Arquivo `{CSV_PATH}` não encontrado. Coloque-o na raiz do projeto.")
        return

    df_raw = load_data(CSV_PATH)
    vs_raw = load_virtual_sessions(CSV_PATH)
    dest_raw = load_destaques(CSV_PATH)
    dc_raw = load_destaque_cancelamentos(CSV_PATH)
    va_raw = load_votos_alterados(CSV_PATH)
    venue_raw = load_case_venue(CSV_PATH)
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
        "👤 Relatores",
        "📈 Complexidade",
        "🖥️ Sessões Virtuais",
        "⚡ Destaques",
        "🚫 Cancelamentos de Destaque",
        "👁️ Pedidos de Vista",
        "✏️ Votos Alterados",
        "📋 Situação dos Processos",
        "🔍 Explorar",
    ])

    with tabs[0]:
        render_overview(df)
    with tabs[1]:
        render_temporal(df)
    with tabs[2]:
        render_justices(df)
    with tabs[3]:
        render_complexity(df)
    with tabs[4]:
        render_virtual_sessions(vs_raw, df)
    with tabs[5]:
        render_destaques(dest_raw, df)
    with tabs[6]:
        render_cancelamentos(dc_raw, df)
    with tabs[7]:
        render_vistas(vt_raw, df)
    with tabs[8]:
        render_votos_alterados(va_raw, vs_raw, df)
    with tabs[9]:
        render_situacao_processos(venue_raw, vs_raw, df)
    with tabs[10]:
        render_explorer(df)


if __name__ == "__main__":
    main()
