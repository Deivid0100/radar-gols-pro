"""Radar de Gols Pro 3.0 — Streamlit / football-data.org.

Uso: streamlit run app.py
Chave: digitar no campo protegido (nunca salvar no repositório público).
Este aplicativo faz análises descritivas, não prevê resultados garantidos.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

import csv
import io
import requests
import streamlit as st

API = "https://api.football-data.org/v4"
TZ = ZoneInfo("America/Sao_Paulo")
MAX_LIGAS = 4  # Plano gratuito: até 10 requisições/min; 2 por campeonato.

st.set_page_config(page_title="Radar de Gols Pro 3.0", page_icon="⚽", layout="wide", initial_sidebar_state="collapsed")

CSS = """
<style>
:root {color-scheme:dark}
.stApp {background: #0b121b; color: #e7edf5;}
[data-testid="stHeader"] {background: #0b121b;}
[data-testid="stSidebar"] {background: #111e2d;}
[data-testid="stAppViewContainer"] {background: radial-gradient(circle at 80% 0%, #102c31 0%, #0b121b 32%, #0b121b 100%);}
.block-container {padding-top: 1rem; max-width: 1180px; padding-bottom:3rem;}
h1,h2,h3 {color:#eef8ff!important; letter-spacing:-.025em;}
[data-testid="stMetric"] {background:#122130; border:1px solid #28404e; padding:1.1rem; border-radius:14px;}
[data-testid="stMetricValue"] {color:#74e9b9;}
.stButton button[kind="primary"] {background:#26c894; color:#06140e; border:0; font-weight:800;}
.stButton button {border-radius:10px; min-height:44px; font-weight:650;}
[data-testid="stExpander"] {border:1px solid #28404e; background:#12202c; border-radius:13px;}
[data-testid="stTabs"] button {font-weight:700;}
[data-testid="stDataFrame"] {border:1px solid #28404e; border-radius:12px; overflow:hidden;}
.radar-brand{display:flex;align-items:center;gap:12px; flex-wrap:wrap; margin-bottom:4px;}
.radar-mark{font-size:2rem;background:#123d36;padding:8px 12px;border-radius:14px;}
.radar-title{font-size:1.8rem;font-weight:900;letter-spacing:-.04em;color:#effffb;}
.radar-subtitle{font-size:.89rem;color:#94adb9;}
.radar-pill{color:#a8ffdd;background:#174338;padding:5px 10px;border-radius:18px;font-size:.73rem;font-weight:800;}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px;margin:12px 0 18px;}
.kpi{background:#12212c;border:1px solid #294250;border-radius:14px;padding:16px 17px;}
.kpi .k{font-size:.77rem;letter-spacing:.045em;color:#9db2c0;text-transform:uppercase;}
.kpi .v{font-size:1.72rem;letter-spacing:-.03em;font-weight:850;color:#efffff;line-height:1.3;margin:7px 0 0;}
.kpi .s{font-size:.73rem;color:#71e8b7;margin-top:5px;}
.radar-banner{background:#12342d;border:1px solid #326d5c;border-radius:14px;padding:14px 18px;margin:12px 0 16px;color:#bbf6dd;}
.market-tag{display:inline-block;background:#1c3f3b;color:#9aebc7;padding:6px 11px;border-radius:18px;margin:3px 5px 3px 0;font-weight:750;font-size:.85rem;}
.muted-note{font-size:.82rem;color:#9dafbf;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)
st.markdown('''<div class="radar-brand"><span class="radar-mark">⚽</span><div>
<div class="radar-title">RADAR <span style="color:#39d6a0">PRO 3.0</span> <span class="radar-pill">AUTO</span></div>
<div class="radar-subtitle">Painel de futebol · Confrontos · Mercados · Médias de gols</div></div></div>''', unsafe_allow_html=True)
st.caption("Dados: football-data.org | Horários de Brasília | Análises estatísticas, não garantias de acerto")


def br(num: float, dig: int = 2) -> str:
    return f"{num:.{dig}f}".replace(".", ",")


def get_datetime(match: dict) -> datetime:
    return datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00"))


def local_day(match: dict) -> date:
    return get_datetime(match).astimezone(TZ).date()


def time_br(match: dict) -> str:
    return get_datetime(match).astimezone(TZ).strftime("%H:%M")


@st.cache_data(ttl=1200, show_spinner=False, max_entries=150)
def api_get(path: str, token: str, query: tuple = ()) -> dict:
    if not token.strip():
        raise ValueError("Digite o token do football-data.org.")
    resp = requests.get(
        API + path,
        headers={"X-Auth-Token": token.strip()},
        params=dict(query),
        timeout=30,
    )
    if resp.status_code == 429:
        raise ValueError("Limite de 10 consultas por minuto atingido. Aguarde a liberação do serviço e tente novamente.")
    if resp.status_code in (401, 403):
        raise ValueError("Acesso recusado. Confira o token ou os campeonatos liberados no seu plano.")
    if not resp.ok:
        try:
            reason = resp.json().get("message", "")
        except ValueError:
            reason = resp.text[:150]
        raise ValueError(f"Erro da API ({resp.status_code}): {reason}")
    return resp.json()


def matches_today(dia: date, token: str) -> list[dict]:
    # Busca três dias UTC para não perder partidas próximas da meia-noite local.
    start = (dia - timedelta(days=1)).isoformat()
    end = (dia + timedelta(days=1)).isoformat()
    response = api_get("/matches", token, (("dateFrom", start), ("dateTo", end)))
    return sorted(
        [m for m in response.get("matches", []) if local_day(m) == dia],
        key=get_datetime,
    )


def get_finished_games(comp_id: int, season_start: int, token: str, include_previous: bool) -> tuple[list[dict], list[str]]:
    games: list[dict] = []
    messages: list[str] = []
    years = [season_start, season_start - 1] if include_previous else [season_start]
    for yr in years:
        try:
            response = api_get(
                f"/competitions/{comp_id}/matches", token,
                (("season", yr), ("status", "FINISHED")),
            )
            games.extend(response.get("matches", []))
        except Exception as ex:
            if yr == season_start:
                raise
            messages.append(f"Temporada {yr} não disponível: {ex}")
    return games, messages


def team_history(games: list[dict], team_id: int, venue: str, before: datetime, count: int = 10) -> list[dict]:
    selected: list[dict] = []
    for m in games:
        if m.get("status") != "FINISHED" or get_datetime(m) >= before:
            continue
        home_id = m.get("homeTeam", {}).get("id")
        away_id = m.get("awayTeam", {}).get("id")
        is_home = home_id == team_id
        is_away = away_id == team_id
        if (venue == "home" and not is_home) or (venue == "away" and not is_away):
            continue
        ft = m.get("score", {}).get("fullTime") or {}
        gh, ga = ft.get("home"), ft.get("away")
        if gh is None or ga is None:
            continue
        scored, conceded = (gh, ga) if is_home else (ga, gh)
        selected.append({"date": get_datetime(m), "gf": scored, "ga": conceded, "match": m})
    return sorted(selected, key=lambda x: x["date"], reverse=True)[:count]


def avg(seq: list[dict], field: str) -> float:
    return sum(x[field] for x in seq) / len(seq)


def rate(seq: list[dict], condition) -> float:
    return 100 * sum(bool(condition(x["gf"], x["ga"])) for x in seq) / len(seq)


def signals(h: list[dict], a: list[dict], est_home: float, est_away: float) -> tuple[list[str], dict]:
    total = est_home + est_away
    freq = {
        "Over 1,5": (rate(h, lambda x, y: x + y >= 2) + rate(a, lambda x, y: x + y >= 2)) / 2,
        "Over 2,5": (rate(h, lambda x, y: x + y >= 3) + rate(a, lambda x, y: x + y >= 3)) / 2,
        "Under 2,5": (rate(h, lambda x, y: x + y <= 2) + rate(a, lambda x, y: x + y <= 2)) / 2,
        "Ambas marcam": (rate(h, lambda x, y: x > 0 and y > 0) + rate(a, lambda x, y: x > 0 and y > 0)) / 2,
    }
    markets = []
    if freq["Over 1,5"] >= 75 and total >= 2.10:
        markets.append("Over 1,5")
    if freq["Over 2,5"] >= 58 and total >= 2.50:
        markets.append("Over 2,5")
    if freq["Under 2,5"] >= 65 and total <= 2.40:
        markets.append("Under 2,5")
    if freq["Ambas marcam"] >= 60 and min(est_home, est_away) >= 0.90:
        markets.append("Ambas marcam")
    return markets, freq


def analyze_one(match: dict, games: list[dict]) -> dict | None:
    home_id = match.get("homeTeam", {}).get("id")
    away_id = match.get("awayTeam", {}).get("id")
    if home_id is None or away_id is None:
        return None
    before = get_datetime(match)
    h = team_history(games, home_id, "home", before)
    a = team_history(games, away_id, "away", before)
    if not h or not a:
        return None
    gf_h, ga_h, gf_a, ga_a = avg(h, "gf"), avg(h, "ga"), avg(a, "gf"), avg(a, "ga")
    est_home = (gf_h + ga_a) / 2
    est_away = (gf_a + ga_h) / 2
    market_list, freqs = signals(h, a, est_home, est_away)
    sample = min(len(h), len(a))
    grade = "Amostra boa" if sample >= 8 else "Amostra moderada" if sample >= 5 else "Amostra curta"
    form_home = h[:5]
    form_away = a[:5]
    prev_est = None
    if len(form_home) >= 3 and len(form_away) >= 3:
        prev_est = (avg(form_home, "gf") + avg(form_away, "ga") + avg(form_away, "gf") + avg(form_home, "ga")) / 2
    return {
        "match": match, "home": h, "away": a, "gf_h": gf_h, "ga_h": ga_h,
        "gf_a": gf_a, "ga_a": ga_a, "eh": est_home, "ea": est_away,
        "total": est_home + est_away, "markets": market_list, "freq": freqs,
        "grade": grade, "sample": sample, "trend5": prev_est,
    }


def outcome_for_market(match: dict, market: str) -> bool | None:
    if match.get("status") != "FINISHED":
        return None
    full = match.get("score", {}).get("fullTime") or {}
    x, y = full.get("home"), full.get("away")
    if x is None or y is None:
        return None
    return {
        "Over 1,5": x + y >= 2,
        "Over 2,5": x + y >= 3,
        "Under 2,5": x + y <= 2,
        "Ambas marcam": x > 0 and y > 0,
    }.get(market)


def result_table(items: list[dict]) -> list[dict]:
    rows = []
    for r in items:
        m = r["match"]
        rows.append({
            "Horário": time_br(m), "Campeonato": m["competition"]["name"],
            "Confronto": f"{m['homeTeam']['name']} x {m['awayTeam']['name']}",
            "Casa": round(r["eh"], 2), "Fora": round(r["ea"], 2),
            "Total": round(r["total"], 2),
            "Mercados": ", ".join(r["markets"]) or "Sem sinal",
            "O1,5 %": round(r["freq"]["Over 1,5"]),
            "O2,5 %": round(r["freq"]["Over 2,5"]),
            "Ambas %": round(r["freq"]["Ambas marcam"]),
            "Amostra": f"{len(r['home'])}c / {len(r['away'])}f",
            "Qualidade": r["grade"],
        })
    return rows


for key, initial in {
    "matches": [], "searched_day": None, "analyses": [], "analyzed_day": None,
    "api_notes": [], "token": "", "selected_competitions": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = initial

with st.expander("🔐 Acesso aos jogos e data", expanded=not bool(st.session_state["matches"])):
    token = st.text_input("Token do football-data.org", type="password", key="token",
                          help="Coloque aqui sua chave. Nunca salve o token em um repositório público.")
    day = st.date_input("Data das partidas", value=datetime.now(TZ).date(), format="DD/MM/YYYY")
    col_search, col_help = st.columns([1, 2])
    with col_search:
        search_pressed = st.button("📅 Buscar jogos", type="primary", use_container_width=True)
    with col_help:
        st.caption("Fonte gratuita: acesso limitado a 12 competições, não a todos os jogos do mundo.")

if search_pressed:
    try:
        with st.spinner("Consultando partidas..."):
            found = matches_today(day, token)
        st.session_state.update(matches=found, searched_day=day, analyses=[], analyzed_day=None, api_notes=[])
        if not found:
            st.warning("Nenhum jogo encontrado nas competições disponíveis nesta data.")
    except Exception as exc:
        st.error(str(exc))

matches = st.session_state["matches"] if st.session_state["searched_day"] == day else []
analyses = st.session_state["analyses"] if st.session_state["analyzed_day"] == day else []

st.markdown('''<div class="kpi-grid">
<div class="kpi"><div class="k">Jogos localizados</div><div class="v">%s</div><div class="s">Fonte disponível</div></div>
<div class="kpi"><div class="k">Confrontos calculados</div><div class="v">%s</div><div class="s">Média de gols</div></div>
<div class="kpi"><div class="k">Com sinal de mercado</div><div class="v">%s</div><div class="s">Não é previsão garantida</div></div>
</div>''' % (len(matches), len(analyses), sum(bool(a["markets"]) for a in analyses)), unsafe_allow_html=True)

tab_radar, tab_conf, tab_ligas, tab_result, tab_info = st.tabs([
    "📡 Radar", "⚔️ Confronto", "🏆 Ligas", "📊 Resultados", "ℹ️ Método"
])

with tab_radar:
    st.subheader("Radar automático do dia")
    if not matches:
        st.info("Coloque o token e toque em Buscar jogos para começar.")
    else:
        names_to_ids = {f"{x['competition']['name']} · {x['competition']['code']}": x["competition"]["id"] for x in matches}
        choices = st.multiselect(
            "Selecione os campeonatos para análise automática",
            options=list(names_to_ids),
            default=list(names_to_ids)[:MAX_LIGAS],
            help=f"Analise até {MAX_LIGAS} campeonatos por lote para respeitar a API gratuita.",
        )
        use_prev = st.checkbox("Complementar até 10 jogos com a temporada anterior", value=True,
                               help="Útil no início da temporada. Algumas equipes podem não ter jogado a mesma liga no ano anterior.")
        colrun, colhint = st.columns([1, 2])
        with colrun:
            run = st.button("🚀 ANALISAR CAMPEONATOS", type="primary", use_container_width=True)
        with colhint:
            st.caption("O Radar usa o mesmo cálculo que combinamos: ataque em casa + defesa fora, dividido por 2, e vice-versa.")
        if run:
            if not choices:
                st.warning("Selecione pelo menos um campeonato.")
            elif len(choices) > MAX_LIGAS:
                st.warning(f"Selecione no máximo {MAX_LIGAS} campeonatos por lote para evitar bloqueio por excesso de consultas.")
            elif not token:
                st.warning("Informe o token.")
            else:
                selected_ids = {names_to_ids[v] for v in choices}
                selected = [m for m in matches if m["competition"]["id"] in selected_ids]
                batches: dict[tuple[int, int], list[dict]] = {}
                for m in selected:
                    season = m.get("season", {}).get("startDate", "")[:4]
                    if season.isdigit():
                        k = (m["competition"]["id"], int(season))
                        batches.setdefault(k, []).append(m)
                computed, notes = [], []
                bar = st.progress(0, text="Preparando análise...")
                for i, ((comp_id, yr), group) in enumerate(batches.items()):
                    try:
                        all_games, league_notes = get_finished_games(comp_id, yr, token, use_prev)
                        notes.extend([f"{group[0]['competition']['name']}: {s}" for s in league_notes])
                        for match in group:
                            r = analyze_one(match, all_games)
                            if r:
                                computed.append(r)
                            else:
                                notes.append(f"Sem histórico suficiente: {match['homeTeam']['name']} x {match['awayTeam']['name']}")
                    except Exception as e:
                        notes.append(f"{group[0]['competition']['name']}: {e}")
                    bar.progress((i + 1) / max(1, len(batches)), text=f"Campeonatos analisados: {i+1}/{len(batches)}")
                st.session_state.update(
                    analyses=sorted(computed, key=lambda x: x["total"], reverse=True),
                    analyzed_day=day, api_notes=notes,
                )
                st.rerun()

    if analyses:
        st.markdown('''<div class="radar-banner"><b>✓ RADAR PROCESSADO</b><div class="muted-note">Os sinais são filtros estatísticos. Frequências anteriores não equivalem à probabilidade futura nem comprovam valor nas odds.</div></div>''', unsafe_allow_html=True)
        selected_market = st.selectbox("Mercado", ["Todos", "Over 1,5", "Over 2,5", "Under 2,5", "Ambas marcam"])
        only_quality = st.checkbox("Somente amostras com pelo menos 5 jogos em cada lado", value=True)
        min_total = st.slider("Média combinada mínima", min_value=0.0, max_value=5.0, value=0.0, step=0.1)
        filtered = [r for r in analyses if
                    (selected_market == "Todos" or selected_market in r["markets"]) and
                    (not only_quality or r["sample"] >= 5) and r["total"] >= min_total]
        st.caption(f"{len(filtered)} de {len(analyses)} confrontos após os filtros.")
        if filtered:
            table = result_table(filtered)
            st.dataframe(table, use_container_width=True, hide_index=True)
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=list(table[0]))
            writer.writeheader()
            writer.writerows(table)
            st.download_button("⬇️ Exportar tabela CSV", data=output.getvalue().encode("utf-8-sig"),
                               file_name=f"radar_pro_{day.isoformat()}.csv", mime="text/csv")
        else:
            st.info("Nenhum confronto atende a esses filtros. Reduza os filtros para visualizar mais resultados.")
    elif matches:
        st.caption("Escolha os campeonatos e toque em ANALISAR CAMPEONATOS.")
    if st.session_state["api_notes"] and st.session_state["analyzed_day"] == day:
        with st.expander("Avisos de cobertura e amostras"):
            for msg in st.session_state["api_notes"]:
                st.write("• " + msg)

with tab_conf:
    st.subheader("Confronto detalhado")
    if not analyses:
        st.info("Faça uma análise na aba Radar para comparar as equipes.")
    else:
        by_label = {f"{time_br(r['match'])} · {r['match']['homeTeam']['name']} x {r['match']['awayTeam']['name']}": r for r in analyses}
        match_label = st.selectbox("Escolha um jogo", options=list(by_label))
        r = by_label[match_label]
        m = r["match"]
        home, away = m["homeTeam"]["name"], m["awayTeam"]["name"]
        st.markdown(f"### {escape(home)} × {escape(away)}")
        st.caption(f"{escape(m['competition']['name'])} · {time_br(m)} · {r['grade']}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Mandante", br(r["eh"]))
        c2.metric("TOTAL DE GOLS", br(r["total"]))
        c3.metric("Visitante", br(r["ea"]))
        st.markdown("**Nossa conta, linha por linha:**")
        st.code(
            f"{home}: ({br(r['gf_h'])} marcados + {br(r['ga_a'])} sofridos pelo adversário) ÷ 2 = {br(r['eh'])}\n"
            f"{away}: ({br(r['gf_a'])} marcados + {br(r['ga_h'])} sofridos pelo adversário) ÷ 2 = {br(r['ea'])}\n"
            f"TOTAL COMBINADO = {br(r['total'])}", language=None,
        )
        st.write(f"Amostra: **{len(r['home'])} jogos de {home} em casa** e **{len(r['away'])} de {away} fora**.")
        if r["sample"] < 5:
            st.warning("Amostra curta: use apenas para observação, não como entrada forte.")
        if r["trend5"] is not None:
            st.write(f"Tendência de gols com os últimos 5 de cada equipe: **{br(r['trend5'])}**")
        gap = r["eh"] - r["ea"]
        if gap > 0.6:
            st.caption("Mandante apresenta maior média de gols estimados; isso não basta para prever vitória.")
        elif gap < -0.6:
            st.caption("Visitante apresenta maior média de gols estimados; isso não basta para prever vitória.")
        st.markdown("#### Mercados e histórico")
        freq_df = [
            {"Mercado": k, "Frequência histórica (%)": round(v, 1),
             "Sinal": "Investigar" if k in r["markets"] else "Sem sinal"}
            for k, v in r["freq"].items()
        ]
        st.dataframe(freq_df, hide_index=True, use_container_width=True)
        if r["markets"]:
            st.markdown(" ".join(f'<span class="market-tag">{escape(x)}</span>' for x in r["markets"]), unsafe_allow_html=True)
        else:
            st.caption("Sem sinal histórico suficiente para os filtros definidos.")
        with st.expander("Comparar com uma odd (manual)"):
            market = st.selectbox("Mercado da odd", list(r["freq"]), key="market_odd")
            odd = st.number_input("Odd da casa", min_value=1.01, max_value=50.0, value=1.75, step=0.05)
            st.write(f"Probabilidade implícita da odd: **{br(100/odd,1)}%**")
            st.write(f"Frequência observada (amostra): **{br(r['freq'][market],1)}%**")
            st.caption("Não chame essa diferença de 'value': frequência pequena não é probabilidade calibrada; odds incluem margem da casa.")
        c_home, c_away = st.columns(2)
        for column, caption, seq in [(c_home, "Últimos mandante em casa", r["home"]), (c_away, "Últimos visitante fora", r["away"])]:
            with column:
                st.markdown("**" + caption + "**")
                hist = [{"Data": item["date"].astimezone(TZ).strftime("%d/%m"),
                                      "Feitos": item["gf"], "Sofridos": item["ga"]} for item in seq]
                st.dataframe(hist, hide_index=True, use_container_width=True)
        st.markdown("#### Confrontos diretos disponíveis")
        combined = {j["match"]["id"]: j["match"] for j in r["home"] + r["away"]}
        h2h = [x for x in combined.values() if
               {x["homeTeam"].get("id"), x["awayTeam"].get("id")} ==
               {m["homeTeam"].get("id"), m["awayTeam"].get("id")}]
        if h2h:
            for x in sorted(h2h, key=get_datetime, reverse=True)[:5]:
                ft = x.get("score", {}).get("fullTime") or {}
                st.caption(f"{get_datetime(x).astimezone(TZ).strftime('%d/%m/%Y')} · {x['homeTeam']['name']} {ft.get('home','?')} × {ft.get('away','?')} {x['awayTeam']['name']}")
        else:
            st.caption("Nenhum confronto direto nesta amostra de partidas.")

with tab_ligas:
    st.subheader("Campeonatos disponíveis na busca")
    if matches:
        overview = []
        for name in sorted({x["competition"]["name"] for x in matches}):
            league_games = [x for x in matches if x["competition"]["name"] == name]
            computed_league = [x for x in analyses if x["match"]["competition"]["name"] == name]
            overview.append({"Campeonato": name, "Jogos na data": len(league_games), "Calculados": len(computed_league)})
        st.dataframe(overview, use_container_width=True, hide_index=True)
    else:
        st.info("Busque os jogos para visualizar as ligas cobertas pela sua conta.")
    st.caption("O plano gratuito do football-data.org não cobre ligas pequenas de todo o mundo. Mais campeonatos exigem outras fontes ou plano superior.")

with tab_result:
    st.subheader("Conferência dos resultados")
    if not analyses:
        st.info("Depois de analisar jogos, os resultados finalizados serão comparados com os sinais disponíveis na consulta.")
    else:
        evaluation = []
        for r in analyses:
            m = r["match"]
            for market in r["markets"]:
                won = outcome_for_market(m, market)
                if won is not None:
                    evaluation.append({"Jogo": f"{m['homeTeam']['name']} x {m['awayTeam']['name']}",
                                       "Mercado": market, "Resultado": "Acertou" if won else "Errou"})
        if evaluation:
            st.dataframe(evaluation, hide_index=True, use_container_width=True)
            n_won = sum(x["Resultado"] == "Acertou" for x in evaluation)
            st.metric("Acerto observado (sinais finalizados)", f"{n_won}/{len(evaluation)}")
            st.caption("Sem odds e sem histórico suficiente, acerto percentual isolado não mede rentabilidade. Sessão atual apenas.")
        else:
            st.info("Não há sinais com placar finalizado nesta consulta. Para testar historicamente, selecione uma data passada, busque e analise os jogos.")

with tab_info:
    st.subheader("Como funciona o Radar")
    st.markdown("""
    **1.** Busca jogos do dia nas competições liberadas pela sua chave.

    **2.** Carrega partidas finalizadas da liga (temporada atual e, se você marcar, anterior), sempre descartando as disputadas depois do jogo analisado.

    **3.** Separa até 10 jogos do mandante em casa e 10 do visitante fora.

    **4.** Calcula o mandante como `(gols que fez em casa + gols sofridos pelo visitante fora) / 2` e o visitante no cruzamento inverso.

    **5.** Mostra as frequências históricas de Over 1,5 / Over 2,5 / Under 2,5 / Ambas marcam. Os sinais são regras fixas para **investigar**, não garantias nem probabilidades calibradas.
    """)
    st.warning("Não há modelo de Poisson, promessa de acerto nem aposta automática. As métricas não substituem cotação, escalação, motivação, qualidade dos adversários e gerenciamento de risco.")
    st.caption("Para alterar o programa, atualize app.py no GitHub. O Streamlit Community Cloud sincroniza o código automaticamente.")
