import streamlit as st
import requests
from datetime import date

st.set_page_config(page_title="Radar de Gols Pro", page_icon="⚽")
st.title("⚽ Radar de Gols Pro")
st.caption("Análise estatística de futebol")

API = "https://v3.football.api-sports.io"

def buscar(endpoint, params, chave):
    r = requests.get(
        API + endpoint,
        headers={"x-apisports-key": chave},
        params=params,
        timeout=20
    )
    r.raise_for_status()
    dados = r.json()
    if dados.get("errors"):
        raise ValueError(str(dados["errors"]))
    return dados.get("response", [])

def medias(time, liga, temporada, local, chave):
    jogos = buscar("/fixtures", {
        "team": time, "league": liga,
        "season": temporada, "last": 30,
        "status": "FT"
    }, chave)
    feitos = sofridos = quantidade = 0
    for jogo in jogos:
        casa = jogo["teams"]["home"]["id"] == time
        if (local == "casa" and not casa) or (
            local == "fora" and casa
        ):
            continue
        gols = jogo["goals"]
        if gols["home"] is None or gols["away"] is None:
            continue
        feitos += gols["home"] if casa else gols["away"]
        sofridos += gols["away"] if casa else gols["home"]
        quantidade += 1
    if not quantidade:
        return None
    return feitos / quantidade, sofridos / quantidade, quantidade

chave = st.text_input("Chave API-Football", type="password")
dia = st.date_input("Data dos jogos", date.today())

if st.button("Buscar jogos"):
    if not chave:
        st.warning("Informe sua chave API-Football.")
    else:
        try:
            jogos = buscar("/fixtures", {
                "date": dia.isoformat()
            }, chave)
            st.session_state["jogos"] = jogos
        except Exception as erro:
            st.error(str(erro))

jogos = st.session_state.get("jogos", [])
st.write("Jogos encontrados:", len(jogos))

for jogo in jogos:
    casa = jogo["teams"]["home"]
    fora = jogo["teams"]["away"]
    liga = jogo["league"]
    titulo = casa["name"] + " x " + fora["name"]
    with st.expander(titulo):
        if st.button("Analisar", key=jogo["fixture"]["id"]):
            try:
                a = medias(casa["id"], liga["id"],
                           liga["season"], "casa", chave)
                b = medias(fora["id"], liga["id"],
                           liga["season"], "fora", chave)
                if not a or not b:
                    st.warning("Dados insuficientes.")
                    continue
                gc = (a[0] + b[1]) / 2
                gf = (b[0] + a[1]) / 2
                total = gc + gf
                st.write("Mandante:", round(gc, 2))
                st.write("Visitante:", round(gf, 2))
                st.metric("Média combinada", f"{total:.2f}")
                st.caption(
                    f"Amostra: {a[2]} jogos casa e {b[2]} fora"
                )
                if min(a[2], b[2]) < 5:
                    st.warning("Amostra pequena.")
                if total >= 2.7:
                    mercado = "Investigar Over 2,5"
                elif total >= 2:
                    mercado = "Investigar Over 1,5"
                else:
                    mercado = "Investigar Under 2,5"
                st.info(mercado)
                st.caption(
                    "Média não é probabilidade nem garantia."
                )
            except Exception as erro:
                st.error(str(erro))

