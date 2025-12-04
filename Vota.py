import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta

# ------------------ CONFIGURAÇÕES ------------------
MIN_VOTOS = 0
TEMPO_ESPERA_MIN = 0
MOSTRAR_BRANCO_NULO = 1   # 1 = mostra branco/nulo em cada eleição | 0 = esconde branco/nulo por eleição

# ------------------ CONEXÃO ------------------
def conectar():
    return psycopg2.connect(
        host="aws-0-sa-east-1.pooler.supabase.com",
        dbname="postgres",
        user="postgres.ixyzgjqwjmqiubjbbxsc",
        password="5Ha4cC2u*LP+qDT",
        port="5432"
    )

# ------------------ BUSCAR ELEIÇÕES ------------------
def buscar_eleicoes():
    conn = conectar()
    df = pd.read_sql("SELECT * FROM eleicoes ORDER BY id", conn)
    conn.close()
    return df

# ------------------ BUSCAR CANDIDATOS ------------------
def buscar_candidatos(id_eleicao):
    conn = conectar()
    df = pd.read_sql(f"SELECT * FROM candidatos WHERE id_eleicao = {id_eleicao}", conn)
    conn.close()
    return df

# ------------------ SALVAR VOTO ------------------
def salvar_voto(id_eleicao, nome_voto):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO votos (id_eleicao, nome_voto)
        VALUES (%s, %s)
    """, (id_eleicao, nome_voto))
    conn.commit()
    conn.close()

# ------------------ BUSCAR RESULTADOS ------------------
def buscar_resultados(id_eleicao):
    conn = conectar()
    df = pd.read_sql(f"""
        SELECT nome_voto, COUNT(*) as votos 
        FROM votos 
        WHERE id_eleicao = {id_eleicao} 
        GROUP BY nome_voto
        ORDER BY votos DESC
    """, conn)
    conn.close()
    return df

# ------------------ INTERFACE ------------------
st.title("🗳️ Sistema de Votação")

eleicoes = buscar_eleicoes()

# ------------------ BOTÃO BRANCO/NULO GERAL ------------------
st.markdown("### 🟦 Registrar BRANCO/NULO para todas eleições")
if st.button("🚫 Votar BRANCO/NULO para todas"):
    for _, row in eleicoes.iterrows():
        salvar_voto(row["id"], "BRANCO/NULO")
    st.success("Votos BRANCO/NULO registrados!")

# ------------------ LOOP DAS ELEIÇÕES ------------------
for _, eleicao in eleicoes.iterrows():
    st.markdown(f"## 🗂️ {eleicao['titulo']}")
    
    candidatos = buscar_candidatos(eleicao["id"])

    # Remove BRANCO/NULO da lista SE estiver desativado
    if MOSTRAR_BRANCO_NULO == 0:
        candidatos = candidatos[candidatos["nome"] != "BRANCO/NULO"]

    opcoes = candidatos["nome"].tolist()

    escolha = st.radio(f"Escolha sua opção para {eleicao['titulo']}", opcoes, index=None, key=f"radio_{eleicao['id']}")

    if st.button(f"Confirmar voto em {eleicao['titulo']}", key=f"btn_{eleicao['id']}"):
        if escolha:
            salvar_voto(eleicao["id"], escolha)
            st.success(f"Voto em **{escolha}** registrado!")
        else:
            st.warning("Selecione uma opção para votar.")

    # ---------------- RESULTADO ----------------
    st.markdown("### 📊 Resultado parcial")
    resultados = buscar_resultados(eleicao["id"])

    # Oculta frase de BRANCO/NULO APENAS quando MOSTRAR_BRANCO_NULO = 1
    if MOSTRAR_BRANCO_NULO == 0:
        resultados = resultados[resultados["nome_voto"] != "BRANCO/NULO"]

    st.dataframe(resultados)

    # Frase total BRANCO/NULO (só aparece quando MOSTRAR_BRANCO_NULO = 0)
    if MOSTRAR_BRANCO_NULO == 0:
        total_bn = resultados[resultados["nome_voto"] == "BRANCO/NULO"]["votos"].sum()
        st.info(f"Total de eleitores que votaram BRANCO/NULO: **{total_bn}**")

st.markdown("---")
st.markdown("<div style='text-align:center;color:gray;font-size:14px;'>👨‍💻 Desenvolvido por <b>Leonardo Dutra</b></div>", unsafe_allow_html=True)
