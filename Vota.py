import streamlit as st
import psycopg2
from dotenv import load_dotenv
from datetime import datetime
import os

# --- Carregar variáveis do .env ---
load_dotenv()
HOST = os.getenv("SUPABASE_HOST")
DBNAME = os.getenv("SUPABASE_DB")
USER = os.getenv("SUPABASE_USER")
PASSWORD = os.getenv("SUPABASE_PASSWORD")
PORT = os.getenv("SUPABASE_PORT")

# --- Conexão com o banco ---
try:
    conn = psycopg2.connect(
        host=HOST,
        dbname=DBNAME,
        user=USER,
        password=PASSWORD,
        port=PORT
    )
    cur = conn.cursor()
except Exception as e:
    st.error(f"Erro ao conectar ao banco: {e}")
    st.stop()

# --- Login ---
if "logged_in" not in st.session_state:
    st.subheader("Login do Eleitor")
    nome_input = st.text_input("Nome completo")
    crea_input = st.text_input("Número do CREA")
    if st.button("Entrar"):
        if nome_input.strip() == "" or crea_input.strip() == "":
            st.error("Preencha ambos os campos.")
        else:
            # Verifica se o eleitor existe
            cur.execute("SELECT id FROM eleitores WHERE nome=%s AND crea=%s", (nome_input.strip(), crea_input.strip()))
            res = cur.fetchone()
            if res:
                st.session_state["eleitor_id"] = res[0]
                st.session_state["logged_in"] = True
            else:
                st.error("Eleitor não encontrado. Cadastre no banco primeiro.")

# --- Fluxo de votação ---
if st.session_state.get("logged_in"):
    eleitor_id = st.session_state["eleitor_id"]

    st.info(f"Eleitor ID: **{eleitor_id}**")

    # Carrega eleições ativas
    cur.execute("SELECT id, titulo FROM eleicoes WHERE ativa=true ORDER BY id")
    eleicoes = cur.fetchall()

    votos_para_registrar = []

    st.subheader("Registrar votos em todas as eleições ativas")
    for eleicao in eleicoes:
        eleicao_id, titulo = eleicao
        # Verifica se o eleitor já votou nesta eleição
        cur.execute(
            "SELECT 1 FROM votos_registro WHERE eleitor_id=%s AND eleicao_id=%s",
            (eleitor_id, eleicao_id)
        )
        if cur.fetchone():
            st.success(f"✅ Já votou na eleição {titulo}")
        else:
            # Carrega candidatos
            cur.execute("SELECT id, nome FROM candidatos WHERE eleicao_id=%s ORDER BY id", (eleicao_id,))
            candidatos = cur.fetchall()
            nomes = [c[1] for c in candidatos]
            if nomes:
                escolhido = st.radio(f"Escolha seu candidato para {titulo}:", nomes, key=eleicao_id)
                votos_para_registrar.append((eleicao_id, candidatos[nomes.index(escolhido)][0]))
            else:
                st.warning(f"Nenhum candidato cadastrado para {titulo}")

    # Botão para confirmar todos os votos
    if votos_para_registrar and st.button("Confirmar todos os votos"):
        try:
            for eleicao_id, candidato_id in votos_para_registrar:
                # Insere voto secreto
                cur.execute(
                    "INSERT INTO votos (eleicao_id, candidato_id) VALUES (%s, %s)",
                    (eleicao_id, candidato_id)
                )
                # Registra quem votou
                cur.execute(
                    "INSERT INTO votos_registro (eleitor_id, eleicao_id) VALUES (%s, %s)",
                    (eleitor_id, eleicao_id)
                )
            conn.commit()
            st.success("✅ Votos registrados com sucesso!")
        except Exception as e:
            conn.rollback()
            st.error(f"Erro ao registrar votos: {e}")
