import streamlit as st
import requests
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title="Radar de Gols Pro", page_icon="⚽")
st.title("⚽ Radar de Gols Pro")
st.caption("Médias de gols com jogos reais do football-data.org")

BASE = "https://api.football-data.org/v4"
FUSO = ZoneInfo("America/Sao_Paulo")

@st.cache_data(ttl=600, show_spinner=False)
def consultar(caminho, chave, parametros=()):
    resposta = requests.get(
        BASE + caminho,
        headers={"X-Auth-Token": chave},
        params=dict(parametros),
        timeout=25,
    )
    if resposta.status_code == 429:
        raise ValueError("Limite de consultas atingido. Tente novamente depois.")
    if not resposta.ok:
        raise ValueError(
            "Erro da API (" + str(resposta.status_code) + "): "
            + resposta.text[:180]
        )
    return resposta.json()

def instante(jogo):
    return datetime.fromisoformat(jogo["utcDate"].replace("Z", "+00:00"))

def historico(jogos, time_id, local, competicao_id, antes):
    linhas = []
    for jogo in jogos:
        if jogo.get("status") != "FINISHED":
            continue
        if jogo.get("competition", {}).get("id") != competicao_id:
            continue
        if instante(jogo) >= antes:
            continue
        casa = jogo.get("homeTeam", {}).get("id") == time_id
        fora = jogo.get("awayTeam", {}).get("id") == time_id
        if (local == "casa" and not casa) or (local == "fora" and not fora):
            continue
        placar = jogo.get("score", {}).get("fullTime", {})
        gh, ga = placar.get("home"), placar.get("away")
        if gh is None or ga is None:
            continue
        marcados, sofridos = (gh, ga) if casa else (ga, gh)
        linhas.append((instante(jogo), marcados, sofridos))
    linhas.sort(reverse=True)
    return linhas[:10]

def media(jogos, pos):
    return sum(j[pos] for j in jogos) / len(jogos)

def frequencia(jogos, condicao):
    return 100 * sum(condicao(j[1], j[2]) for j in jogos) / len(jogos)

chave = st.text_input("Token football-data.org", type="password")
dia = st.date_input("Data dos jogos", value=date.today())
st.caption("Cobertura limitada às competições liberadas no plano gratuito.")

if st.button("Buscar jogos"):
    if not chave.strip():
        st.warning("Insira seu token do football-data.org.")
    else:
        try:
            with st.spinner("Buscando jogos..."):
                dados = consultar(
                    "/matches", chave.strip(),
                    (("dateFrom", dia.isoformat()),
                     ("dateTo", (dia + timedelta(days=2)).isoformat()))
                )
            lista = [j for j in dados.get("matches", [])
                     if instante(j).astimezone(FUSO).date() == dia]
            st.session_state["jogos"] = sorted(lista, key=lambda j: j["utcDate"])
            st.session_state["dia_jogos"] = dia
        except Exception as erro:
            st.error(str(erro))

jogos = st.session_state.get("jogos", [])
if st.session_state.get("dia_jogos") != dia:
    jogos = []

campeonatos = sorted({j["competition"]["name"] for j in jogos})
escolhido = st.selectbox("Campeonato", ["Todos"] + campeonatos)
if escolhido != "Todos":
    jogos = [j for j in jogos if j["competition"]["name"] == escolhido]
st.write("Jogos encontrados:", len(jogos))

for jogo in jogos:
    casa = jogo["homeTeam"]
    fora = jogo["awayTeam"]
    competicao = jogo["competition"]
    horario = instante(jogo).astimezone(FUSO).strftime("%H:%M")
    titulo = horario + " — " + casa["name"] + " x " + fora["name"]
    with st.expander(titulo):
        st.caption(competicao["name"] + " | horário de Brasília")
        if st.button("Analisar médias", key="jogo_" + str(jogo["id"])):
            try:
                with st.spinner("Calculando médias..."):
                    referencia = instante(jogo)
                    partidas_casa = consultar(
                        "/teams/" + str(casa["id"]) + "/matches",
                        chave.strip(), (("status", "FINISHED"), ("limit", "150"))
                    ).get("matches", [])
                    partidas_fora = consultar(
                        "/teams/" + str(fora["id"]) + "/matches",
                        chave.strip(), (("status", "FINISHED"), ("limit", "150"))
                    ).get("matches", [])
                    a = historico(partidas_casa, casa["id"], "casa",
                                 competicao["id"], referencia)
                    b = historico(partidas_fora, fora["id"], "fora",
                                 competicao["id"], referencia)
                if not a or not b:
                    st.warning("Sem resultados suficientes para calcular as médias.")
                    continue
                a_feitos, a_sofridos = media(a, 1), media(a, 2)
                b_feitos, b_sofridos = media(b, 1), media(b, 2)
                estimativa_casa = (a_feitos + b_sofridos) / 2
                estimativa_fora = (b_feitos + a_sofridos) / 2
                total = estimativa_casa + estimativa_fora
                st.write("**" + casa["name"] + "**")
                st.write(f"({a_feitos:.2f} + {b_sofridos:.2f}) ÷ 2 = {estimativa_casa:.2f} gol")
                st.write("**" + fora["name"] + "**")
                st.write(f"({b_feitos:.2f} + {a_sofridos:.2f}) ÷ 2 = {estimativa_fora:.2f} gol")
                st.metric("Média combinada", f"{total:.2f} gols")
                st.caption(f"Amostra: {len(a)} jogos do mandante em casa e {len(b)} do visitante fora, da mesma competição.")
                if min(len(a), len(b)) < 5:
                    st.warning("Amostra pequena. Análise pouco confiável.")
                amostra = a + b
                o15 = frequencia(amostra, lambda g, s: g + s >= 2)
                o25 = frequencia(amostra, lambda g, s: g + s >= 3)
                u25 = 100 - o25
                ambas = frequencia(amostra, lambda g, s: g > 0 and s > 0)
                st.write(f"Frequências observadas: Over 1,5 {o15:.0f}% | Over 2,5 {o25:.0f}% | Under 2,5 {u25:.0f}% | Ambas {ambas:.0f}%")
                mercados = []
                if min(len(a), len(b)) >= 5:
                    if o15 >= 75 and total >= 2.1:
                        mercados.append("Over 1,5")
                    if o25 >= 58 and total >= 2.5:
                        mercados.append("Over 2,5")
                    if u25 >= 65 and total < 2.5:
                        mercados.append("Under 2,5")
                    if ambas >= 60 and min(estimativa_casa, estimativa_fora) >= 0.9:
                        mercados.append("Ambas marcam")
                st.info("Mercados para investigar: " + (", ".join(mercados) if mercados else "sem sinal suficiente"))
                st.caption("Frequências não são probabilidades previstas; médias não garantem gols nem lucro. Compare odds antes de decidir.")
            except Exception as erro:
                st.error(str(erro))
# === RADAR: ANALISAR TODOS OS JOGOS ===
st.divider()
st.subheader("📊 Radar automático do dia")
st.caption("Uma consulta por campeonato, economizando chamadas da API.")

if jogos and st.button("🔎 Analisar todos os jogos", type="primary"):
    grupos = {}
    for j in jogos:
        identificador = (j["competition"]["id"], j["season"]["startDate"][:4])
        grupos.setdefault(identificador, []).append(j)

    if len(grupos) > 8:
        st.warning("Há mais de 8 campeonatos. Escolha um campeonato no filtro.")
    elif not chave.strip():
        st.warning("Informe seu token para analisar.")
    else:
        resultados, avisos = [], []
        with st.spinner("Analisando os campeonatos..."):
            for (liga_id, temporada), grupo in grupos.items():
                try:
                    resposta = consultar(
                        f"/competitions/{liga_id}/matches",
                        chave.strip(),
                        (("season", temporada), ("status", "FINISHED")),
                    )
                    partidas = resposta.get("matches", [])
                    for j in grupo:
                        a = historico(partidas, j["homeTeam"]["id"], "casa", liga_id, instante(j))
                        b = historico(partidas, j["awayTeam"]["id"], "fora", liga_id, instante(j))
                        if not a or not b:
                            avisos.append(j["homeTeam"]["name"] + " x " + j["awayTeam"]["name"] + ": sem histórico suficiente")
                            continue

                        am = sum(x[1] for x in a) / len(a)
                        asf = sum(x[2] for x in a) / len(a)
                        bm = sum(x[1] for x in b) / len(b)
                        bsf = sum(x[2] for x in b) / len(b)

                        ec = (am + bsf) / 2
                        ef = (bm + asf) / 2
                        total = ec + ef
                        historicos = a + b

                        o15 = frequencia(historicos, lambda g, s: g + s >= 2)
                        o25 = frequencia(historicos, lambda g, s: g + s >= 3)
                        ambas = frequencia(historicos, lambda g, s: g > 0 and s > 0)
                        u25 = 100 - o25

                        mercados = []
                        if o15 >= 75 and total >= 2.1:
                            mercados.append("Over 1,5")
                        if o25 >= 58 and total >= 2.5:
                            mercados.append("Over 2,5")
                        if ambas >= 60 and min(ec, ef) >= 0.9:
                            mercados.append("Ambas marcam")
                        if u25 >= 65 and total < 2.5:
                            mercados.append("Under 2,5")

                        resultados.append({
                            "jogo": j, "am": am, "asf": asf,
                            "bm": bm, "bsf": bsf, "ec": ec, "ef": ef,
                            "total": total, "o15": o15, "o25": o25,
                            "ambas": ambas, "u25": u25,
                            "na": len(a), "nb": len(b),
                            "mercados": mercados,
                        })
                except Exception as erro:
                    avisos.append("Campeonato " + str(liga_id) + ": " + str(erro))

        st.session_state["radar_resultados"] = sorted(
            resultados, key=lambda x: x["total"], reverse=True
        )
        st.session_state["radar_avisos"] = avisos
        st.session_state["radar_contexto"] = (dia.isoformat(), escolhido)

if st.session_state.get("radar_contexto") == (dia.isoformat(), escolhido):
    resultados = st.session_state.get("radar_resultados", [])
    if resultados:
        tabela = []
        for r in resultados:
            j = r["jogo"]
            curta = min(r["na"], r["nb"]) < 5
            tabela.append({
                "Jogo": j["homeTeam"]["name"] + " x " + j["awayTeam"]["name"],
                "Média": round(r["total"], 2),
                "Mercados": ", ".join(r["mercados"]) or "Sem sinal",
                "Amostra": f"{r['na']} casa / {r['nb']} fora",
                "Atenção": "Poucos jogos" if curta else "OK",
            })

        st.dataframe(tabela, hide_index=True, use_container_width=True)
        st.caption("Ordenado pela média estimada, não pela chance de lucro.")

        for r in resultados:
            j = r["jogo"]
            with st.expander(j["homeTeam"]["name"] + " x " + j["awayTeam"]["name"] + " — detalhes"):
                st.write(f"Mandante: ({r['am']:.2f} + {r['bsf']:.2f}) ÷ 2 = **{r['ec']:.2f}**")
                st.write(f"Visitante: ({r['bm']:.2f} + {r['asf']:.2f}) ÷ 2 = **{r['ef']:.2f}**")
                st.metric("Total combinado", f"{r['total']:.2f} gols")
                st.write(f"Over 1,5: {r['o15']:.0f}% | Over 2,5: {r['o25']:.0f}%")
                st.write(f"Under 2,5: {r['u25']:.0f}% | Ambas: {r['ambas']:.0f}%")
                if min(r["na"], r["nb"]) < 5:
                    st.warning("Amostra pequena: não classificar como entrada forte.")

    if st.session_state.get("radar_avisos"):
        with st.expander("Jogos sem análise ou erros"):
            for aviso in st.session_state["radar_avisos"]:
                st.write("• " + aviso)
