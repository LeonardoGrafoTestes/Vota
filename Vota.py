import streamlit as st
import psycopg2
import hashlib
import datetime
import os
import random
import string

# ===============================
# CONEXÃO BANCO
# ===============================
def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        dbname=os.getenv("DB_NAME", "votacao"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASS", "postgres"),
        port=os.getenv("DB_PORT", "5432")
    )

# ===============================
# GERAR TOKEN
# ===============================
def gerar_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=16))

# ===============================
# SALVAR VOTO
# ===============================
def salvar_voto(eleicao_id, token_hash, voto_hash):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO votos (eleicao_id, token_hash, vote_hash, datahora)
            VALUES (%s, %s, %s, %s)
        """, (eleicao_id, token_hash, voto_hash, datetime.datetime.now()))
        conn.commit()
    except Exception as e:
        st.error(f"Erro ao registrar voto: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

# ===============================
# CARREGAR ELEIÇÕES
# ===============================
def carregar_eleicoes():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nome FROM eleicoes ORDER BY id")
    eleicoes = cur.fetchall()
    cur.close()
    conn.close()
    return eleicoes

# ===============================
# CARREGAR CANDIDATOS
# ===============================
def carregar_candidatos(eleicao_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nome FROM candidatos WHERE eleicao_id = %s", (eleicao_id,))
    candidatos = cur.fetchall()
    cur.close()
    conn.close()
    return candidatos

# ===============================
# INTERFACE STREAMLIT
# ===============================
st.set_page_config(page_title="Sistema de Votação", layout="centered")

if "etapa" not in st.session_state:
    st.session_state.etapa = "inicio"
if "eleicoes" not in st.session_state:
    st.session_state.eleicoes = carregar_eleicoes()
if "indice_eleicao" not in st.session_state:
    st.session_state.indice_eleicao = 0
if "token" not in st.session_state:
    st.session_state.token = None
if "voto_selecionado" not in st.session_state:
    st.session_state.voto_selecionado = None

# ===============================
# ETAPA 1 - INÍCIO
# ===============================
if st.session_state.etapa == "inicio":
    st.title("Sistema de Votação")
    st.write("Bem-vindo(a)! Clique abaixo para iniciar sua votação.")
    if st.button("Iniciar votação"):
        st.session_state.token = gerar_token()
        st.session_state.etapa = "votacao"
        st.rerun()

# ===============================
# ETAPA 2 - VOTAÇÃO
# ===============================
elif st.session_state.etapa == "votacao":
    if st.session_state.indice_eleicao >= len(st.session_state.eleicoes):
        st.success("Você já votou em todas as eleições disponíveis!")
        st.session_state.etapa = "fim"
        st.rerun()

    eleicao_id, eleicao_nome = st.session_state.eleicoes[st.session_state.indice_eleicao]

    st.header(f"Eleição: {eleicao_nome}")
    candidatos = carregar_candidatos(eleicao_id)

    escolha = st.radio("Escolha seu candidato:", [c[1] for c in candidatos], key=f"eleicao_{eleicao_id}")

    if st.button("Confirmar voto"):
        st.session_state.voto_selecionado = escolha
        st.session_state.etapa = "confirmacao"
        st.rerun()

# ===============================
# ETAPA 3 - CONFIRMAÇÃO
# ===============================
elif st.session_state.etapa == "confirmacao":
    eleicao_id, eleicao_nome = st.session_state.eleicoes[st.session_state.indice_eleicao]

    st.warning(f"Você está prestes a confirmar seu voto para a eleição: {eleicao_nome}")
    st.write(f"**Sua escolha:** {st.session_state.voto_selecionado}")

    if st.button("Confirmar e registrar voto"):
        token_hash = hashlib.sha256(st.session_state.token.encode()).hexdigest()
        voto_hash = hashlib.sha256(st.session_state.voto_selecionado.encode()).hexdigest()
        salvar_voto(eleicao_id, token_hash, voto_hash)

        st.success("Voto registrado com sucesso!")
        st.session_state.indice_eleicao += 1

        if st.session_state.indice_eleicao < len(st.session_state.eleicoes):
            if st.button("Próxima eleição"):
                st.session_state.etapa = "votacao"
                st.rerun()
        else:
            st.session_state.etapa = "fim"
            st.rerun()

    if st.button("Voltar e escolher outro candidato"):
        st.session_state.etapa = "votacao"
        st.rerun()

# ===============================
# ETAPA 4 - FIM
# ===============================
elif st.session_state.etapa == "fim":
    st.title("Fim da votação")
    st.success("Obrigado por participar da votação!")
    st.write("Seu voto foi registrado com sucesso e permanece **secreto**.")
