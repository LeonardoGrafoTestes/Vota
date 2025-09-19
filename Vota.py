import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime

# ------------------ CONEXÃO ------------------
def get_connection():
    if "conn" not in st.session_state:
        try:
            supabase = st.secrets["connections"]["supabase"]
            st.session_state["conn"] = psycopg2.connect(
                host=supabase["host"],
                port=int(supabase["port"]),
                dbname=supabase["dbname"],
                user=supabase["user"],
                password=supabase["password"]
            )
        except Exception as e:
            st.error(f"Erro ao conectar ao banco: {e}")
            return None
    return st.session_state["conn"]

# ------------------ FUNÇÕES ------------------
def get_eleicoes():
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT id, titulo, data_inicio FROM eleicoes WHERE ativa = true ORDER BY id")
        rows = cur.fetchall()
        cur.close()
        return rows
    return []

def get_candidatos(eleicao_id):
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT id, nome FROM candidatos WHERE eleicao_id = %s", (eleicao_id,))
        rows = cur.fetchall()
        cur.close()
        return rows
    return []

def registrar_votos(eleitor_id, escolhas):
    """
    escolhas = dict { eleicao_id: candidato_id }
    """
    conn = get_connection()
    if conn:
        cur = conn.cursor()

        # Verifica se já votou em alguma dessas eleições
        cur.execute("SELECT eleicao_id FROM votos_registro WHERE eleitor_id = %s AND eleicao_id = ANY(%s)",
                    (eleitor_id, list(escolhas.keys())))
        ja_votadas = [row[0] for row in cur.fetchall()]
        if ja_votadas:
            cur.close()
            return False, f"Você já votou nas eleições: {ja_votadas}"

        # Grava todos os votos (secretos)
        for eleicao_id, candidato_id in escolhas.items():
            cur.execute("INSERT INTO votos (eleicao_id, candidato_id, datahora) VALUES (%s,%s,%s)",
                        (eleicao_id, candidato_id, datetime.now()))
            cur.execute("INSERT INTO votos_registro (eleitor_id, eleicao_id, datahora) VALUES (%s,%s,%s)",
                        (eleitor_id, eleicao_id, datetime.now()))

        conn.commit()
        cur.close()
        return True, "Todos os votos foram registrados com sucesso!"
    return False, "Erro de conexão."

# ------------------ INTERFACE ------------------
st.title("🗳️ Sistema de Votação Online")

menu = st.sidebar.radio("Navegação", ["Login", "Votar"])

# LOGIN
if menu == "Login":
    st.subheader("🔑 Login do Eleitor")
    nome = st.text_input("Nome completo")
    crea = st.text_input("Número do CREA (apenas números)")
    email = st.text_input("Email (opcional)")

    if st.button("Entrar"):
        if not nome or not crea:
            st.error("Nome e CREA são obrigatórios.")
        else:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT id, nome FROM eleitores WHERE crea = %s", (crea,))
            eleitor = cur.fetchone()
            if eleitor:
                st.session_state["eleitor_id"] = eleitor[0]
                st.session_state["nome"] = eleitor[1]
            else:
                cur.execute(
                    "INSERT INTO eleitores (nome, crea, email, data_cadastro) VALUES (%s,%s,%s,%s) RETURNING id",
                    (nome, crea, email, datetime.now())
                )
                eleitor_id = cur.fetchone()[0]
                conn.commit()
                st.session_state["eleitor_id"] = eleitor_id
                st.session_state["nome"] = nome
            cur.close()
            st.success(f"Bem-vindo(a), {st.session_state['nome']}!")

# VOTAR
elif menu == "Votar":
    if "eleitor_id" not in st.session_state:
        st.warning("⚠️ Faça login primeiro!")
    else:
        st.subheader("🗳️ Votação")
        eleicoes = get_eleicoes()
        if not eleicoes:
            st.info("Nenhuma eleição ativa.")
        else:
            escolhas = {}
            for eleicao_id, titulo, data_inicio in eleicoes:
                st.write(f"### {titulo}")
                candidatos = get_candidatos(eleicao_id)

                if not candidatos:
                    st.info("Nenhum candidato cadastrado.")
                    continue

                escolhido = st.radio(
                    f"Escolha seu candidato para {titulo}:",
                    [f"{c[0]} - {c[1]}" for c in candidatos],
                    key=f"eleicao_{eleicao_id}"
                )

                if escolhido:
                    escolhas[eleicao_id] = int(escolhido.split(" - ")[0])

            # Só habilita confirmar se todas as eleições receberam voto
            if len(escolhas) == len(eleicoes):
                if st.button("✅ Confirmar todos os votos"):
                    sucesso, msg = registrar_votos(st.session_state["eleitor_id"], escolhas)
                    if sucesso:
                        st.success(msg)
                        st.experimental_rerun()
                    else:
                        st.error(msg)
            else:
                st.info("Você precisa votar em todas as eleições antes de confirmar.")
