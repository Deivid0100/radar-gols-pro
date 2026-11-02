import csv
import io
import re
import zipfile
from datetime import date, datetime, timedelta

import requests
import streamlit as st

URL = "https://codeload.github.com/oladeeayo/open-matchday/zip/refs/heads/master"
st.set_page_config(page_title="Radar de Gols Pro 4", page_icon="⚽", layout="wide")
st.markdown("""<style>
[data-testid="stAppViewContainer"] {background: #0b1423;}
[data-testid="stMetric"] {background: #16263a; border-radius: 12px; padding: 12px;}
</style>""", unsafe_allow_html=True)

def data_valida(valor):
    try:
        return date.fromisoformat(str(valor)[:10])
    except (TypeError, ValueError):
        return None

def numero(valor):
    try:
        return int(valor)
    except (ValueError, TypeError):
        return None

@st.cache_data(ttl=21600, show_spinner=False)
def carregar():
    resposta = requests.get(URL, timeout=90)
    resposta.raise_for_status()
    ligas = {}
    with zipfile.ZipFile(io.BytesIO(resposta.content)) as pacote:
        indice = next((n for n in pacote.namelist() if n.endswith("/LEAGUE_INDEX.md")), None)
        if indice:
            for linha in pacote.read(indice).decode("utf-8").splitlines():
                campos = linha.split("|")
                if len(campos) >= 4 and campos[1].strip().startswith(chr(96)):
                    pasta = campos[1].strip().strip(chr(96))
                    ligas[pasta] = {"nome": campos[2].strip(), "pais": campos[3].strip(),
                                    "resultados": [], "jogos": []}
        for caminho in pacote.namelist():
            achou = re.search(r"/data/([^/]+)/(results|fixtures)_\d+\.csv$", caminho)
            if not achou:
                continue
            pasta, tipo = achou.groups()
            liga = ligas.setdefault(pasta, {"nome": pasta, "pais": "", "resultados": [], "jogos": []})
            conteudo = pacote.read(caminho).decode("utf-8-sig", errors="replace")
            linhas = list(csv.DictReader(io.StringIO(conteudo)))
            if tipo == "results":
                liga["resultados"].extend(r for r in linhas if data_valida(r.get("date"))
                                            and numero(r.get("ft_home")) is not None
                                            and numero(r.get("ft_away")) is not None)
            else:
                liga["jogos"].extend(r for r in linhas if data_valida(r.get("date")))
    if not ligas:
        raise ValueError("Nenhum campeonato foi encontrado na fonte.")
    return ligas

def ultimos(resultados, equipe, local, antes):
    coluna = "home" if local == "casa" else "away"
    jogos = [r for r in resultados if r.get(coluna) == equipe
             and data_valida(r.get("date")) and data_valida(r["date"]) < antes]
    jogos.sort(key=lambda r: r["date"], reverse=True)
    return jogos[:10]

def resumo(jogos, local):
    if not jogos:
        return None
    feitos = "ft_home" if local == "casa" else "ft_away"
    sofridos = "ft_away" if local == "casa" else "ft_home"
    pares = [(numero(j[feitos]), numero(j[sofridos])) for j in jogos]
    pares = [(f, s) for f, s in pares if f is not None and s is not None]
    if not pares:
        return None
    n = len(pares)
    return {"n": n, "gf": sum(f for f, s in pares)/n,
            "ga": sum(s for f, s in pares)/n,
            "o15": sum(f+s >= 2 for f, s in pares)/n,
            "o25": sum(f+s >= 3 for f, s in pares)/n,
            "ambas": sum(f > 0 and s > 0 for f, s in pares)/n}

def analisar(jogo, liga):
    mandante = resumo(ultimos(liga["resultados"], jogo["home"], "casa", data_valida(jogo["date"])), "casa")
    visitante = resumo(ultimos(liga["resultados"], jogo["away"], "fora", data_valida(jogo["date"])), "fora")
    info = {"a": mandante, "b": visitante, "total": None, "mercado": "Sem histórico suficiente"}
    if mandante is None or visitante is None:
        return info
    casa = (mandante["gf"] + visitante["ga"]) / 2
    fora = (visitante["gf"] + mandante["ga"]) / 2
    info.update(casa=casa, fora=fora, total=casa+fora)
    n = mandante["n"] + visitante["n"]
    for campo in ("o15", "o25", "ambas"):
        info[campo] = (mandante[campo]*mandante["n"] + visitante[campo]*visitante["n"])/n
    info["u25"] = 1 - info["o25"]
    if min(mandante["n"], visitante["n"]) < 5:
        info["mercado"] = "Amostra pequena"
        return info
    sinais = []
    if info["total"] >= 2.1 and info["o15"] >= .75:
        sinais.append("Over 1,5")
    if info["total"] >= 2.6 and info["o25"] >= .58:
        sinais.append("Over 2,5")
    if info["total"] < 2.5 and info["u25"] >= .65:
        sinais.append("Under 2,5")
    if min(casa, fora) >= .9 and info["ambas"] >= .60:
        sinais.append("Ambas marcam")
    info["mercado"] = ", ".join(sinais) if sinais else "Sem sinal forte"
    return info

st.title("⚽ RADAR DE GOLS PRO 4.0")
st.caption("Agenda de várias ligas e cruzamento de médias de gols; dados não são ao vivo.")
with st.sidebar:
    dia = st.date_input("Data", datetime.now().date(), format="DD/MM/YYYY")
    dias = st.select_slider("Pesquisar por", options=[1, 3, 7, 14], value=3,
                             format_func=lambda n: str(n) + " dia(s)")
    if st.button("Atualizar base"):
        carregar.clear()
        st.rerun()

try:
    with st.spinner("Buscando jogos e resultados..."):
        ligas = carregar()
except Exception as erro:
    st.error("Erro ao carregar a fonte de dados. Confira sua conexão.")
    st.code(str(erro)[:250])
    st.stop()

fim = dia + timedelta(days=dias-1)
agenda = []
for pasta, liga in ligas.items():
    vistos = set()
    for jogo in liga["jogos"] + liga["resultados"]:
        data_jogo = data_valida(jogo.get("date"))
        if not data_jogo or not dia <= data_jogo <= fim:
            continue
        chave = (jogo.get("date"), jogo.get("home"), jogo.get("away"))
        if not all(chave) or chave in vistos:
            continue
        vistos.add(chave)
        agenda.append((pasta, jogo))

paises = sorted({ligas[p]["pais"] for p, j in agenda if ligas[p]["pais"]})
pais = st.selectbox("País", ["Todos"] + paises)
agenda = [(p, j) for p, j in agenda if pais == "Todos" or ligas[p]["pais"] == pais]
nomes = sorted({ligas[p]["nome"] for p, j in agenda})
campeonato = st.selectbox("Campeonato", ["Todos"] + nomes)
agenda = [(p, j) for p, j in agenda if campeonato == "Todos" or ligas[p]["nome"] == campeonato]
mercado = st.selectbox("Filtrar mercado", ["Todos", "Over 1,5", "Over 2,5", "Under 2,5", "Ambas marcam", "Amostra pequena"])

registros = []
for pasta, jogo in agenda:
    info = analisar(jogo, ligas[pasta])
    if mercado != "Todos" and mercado not in info["mercado"]:
        continue
    registros.append((pasta, jogo, info))
registros.sort(key=lambda x: (x[2]["total"] is None, -(x[2]["total"] or 0)))

c1, c2, c3 = st.columns(3)
c1.metric("Jogos listados", len(agenda))
c2.metric("Com média calculada", sum(x[2]["total"] is not None for x in registros))
c3.metric("Com sinal", sum(x[2]["mercado"] not in ("Amostra pequena", "Sem histórico suficiente", "Sem sinal forte") for x in registros))

st.subheader("📊 Radar automático")
linhas = []
for pasta, jogo, info in registros:
    amostra = (str(info["a"]["n"]) if info["a"] else "0") + "/" + (str(info["b"]["n"]) if info["b"] else "0")
    linhas.append({"Data": jogo["date"], "Hora da base": jogo.get("time", ""),
                   "Liga": ligas[pasta]["nome"], "Jogo": jogo["home"] + " x " + jogo["away"],
                   "Média": round(info["total"], 2) if info["total"] is not None else None,
                   "Mercado a investigar": info["mercado"], "Amostra casa/fora": amostra})
st.dataframe(linhas, use_container_width=True, hide_index=True, height=450)
st.caption("A base é atualizada pelo fornecedor diariamente, não em tempo real. Horários podem estar em outro fuso.")

st.subheader("🔍 Detalhes do confronto")
if registros:
    escolhido = st.selectbox("Escolha o jogo", list(range(len(registros))),
                             format_func=lambda i: registros[i][1]["home"] + " x " + registros[i][1]["away"])
    pasta, jogo, info = registros[escolhido]
    a, b = info["a"], info["b"]
    if a and b:
        st.write(f"**{jogo['home']}:** ({a['gf']:.2f} + {b['ga']:.2f}) ÷ 2 = **{info['casa']:.2f}**")
        st.write(f"**{jogo['away']}:** ({b['gf']:.2f} + {a['ga']:.2f}) ÷ 2 = **{info['fora']:.2f}**")
        st.metric("Total combinado", f"{info['total']:.2f} gols")
        st.write(f"Histórico Over 1,5: {info['o15']:.0%} | Over 2,5: {info['o25']:.0%} | Under 2,5: {info['u25']:.0%} | Ambas: {info['ambas']:.0%}")
        st.write("Jogos analisados (casa/fora):", a["n"], "/", b["n"])
        st.info(info["mercado"])
    else:
        st.warning("Não há resultados anteriores suficientes desse confronto nesta competição.")

st.caption("Fonte: open-matchday (uso pessoal não comercial). Médias e frequências históricas não garantem acertos. Verifique as odds e os horários em fonte oficial.")
