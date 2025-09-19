import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
from urllib.parse import urlparse

# ------------------ CONFIGURAÇÕES ------------------
MIN_VOTOS = 2        # quantidade mínima de votos para liberar resultados
TEMPO_MINUTOS = 10   # tempo mínimo em minutos para liberar resultados após início

# ------------------ CONEXÃO ------------------
def get_connection():
    """Mantém a conexão ativa durante a sessão"""
    if "conn" not in st.session_state:
        try:
            db_url = st.secrets["connections"]["supabase"]["url"]
            
            # Parse da URL
            result = urlparse(db_url)
            conn_params = {
                "dbname": result.path[1:],  # remove a barra inicial
                "user": result.username,
                "password": result.password,
                "host": result.hostname,
                "port": result.port
            }
            st.session_state["conn"] = psycopg2.connect(**conn_params)
        except Exception as e:
            st.error(f"Erro ao conectar ao banco: {e}")
            return None
    return st.session_state["conn"]

# ------------------ FUNÇÕES ------------------
def autenticar_ou_cadastrar_eleitor(nome, crea, email=None):
    """Autentica ou cadastra o eleitor se não existir"""
    if not crea.isdigit():
        st.error("O CREA deve conter apenas números.")
        return None
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT id, nome FROM eleitores WHERE crea = %s", (crea,))
        eleitor = cur.fetchone()
        if eleitor:
            cur.close()
            return eleitor
        else:
            # cadastra novo eleitor
            cur.execute(
                "INSERT INTO eleitores (nome, crea, email, data_cadastro) VALUES (%s,%s,%s,%s) RETURNING id",
                (nome, crea, email, datetime.now())
            )
            eleitor_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            return (eleitor_id, nome)
    return None

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

def registrar_voto(eleitor_id, eleicao_id, candidato_id):
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        # Verifica se já votou
        cur.execute("SELECT 1 FROM votos_registro WHERE eleitor_id = %s AND eleicao_id = %s", (eleitor_id, eleicao_id))
        if cur.fetchone():
            cur.close()
            return False, "Você já votou nesta eleição."

        # Insere voto secreto
        cur.execute("INSERT INTO votos (eleicao_id, candidato_id, datahora) VALUES (%s,%s,%s)", 
                    (eleicao_id, candidato_id, datetime.now()))

        # Marca registro do eleitor
        cur.execute("INSERT INTO votos_registro (eleitor_id, eleicao_id, datahora) VALUES (%s,%s,%s)",
                    (eleitor_id, eleicao_id, datetime.now()))

        conn.commit()
        cur.close()
        return True, "Voto registrado com sucesso!"
    return False, "Erro de conexão."

def get_resultados(eleicao_id, data_inicio):
    """Retorna resultados apenas se MIN_VOTOS atingidos e TEMPO_MINUTOS passados"""
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        # conta votos
        cur.execute("SELECT COUNT(*) FROM votos WHERE eleicao_id = %s", (eleicao_id,))
        total_votos = cur.fetchone()[0]

        if total_votos < MIN_VOTOS:
            cur.close()
            return None, f"Aguardando pelo menos {MIN_VOTOS} votos (atualmente: {total_votos})."

        if datetime.now() < data_inicio + timedelta(minutes=TEMPO_MINUTOS):
            cur.close()
            return None, f"Resultados liberados após {TEMPO_MINUTOS} minutos do início da eleição."

        # busca resultados
        cur.execute("""
            SELECT c.nome, COUNT(v.id) as total_votos
            FROM candidatos c
            LEFT JOIN votos v ON v.candidato_id = c.id
            WHERE c.eleicao_id = %s
            GROUP BY c.nome
            ORDER BY total_votos DESC
        """, (eleicao_id,))
        resultados = cur.fetchall()
        cur.close()
        return resultados, None
    return None, "Erro de conexão."

# ------------------ INTERFACE ------------------
st.title("🗳️ Sistema de Votação Online")
menu = st.sidebar.radio("Navegação", ["Login", "Votar", "Resultados"])

# LOGIN / CADASTRO
if menu == "Login":
    st.subheader("🔑 Login do Eleitor")
    nome = st.text_input("Nome completo")
    crea = st.text_input("Número do CREA (apenas números)")
    email = st.text_input("Email (apenas se for cadastro novo)")

    if st.button("Entrar"):
        if not nome or not crea:
            st.error("Nome e CREA são obrigatórios.")
        else:
            eleitor = autenticar_ou_cadastrar_eleitor(nome, crea, email)
            if eleitor:
                st.session_state["eleitor_id"] = eleitor[0]
                st.session_state["nome"] = eleitor[1]
                st.success(f"Bem-vindo(a), {eleitor[1]}!")
            else:
                st.error("Erro no login ou cadastro.")

# VOTAÇÃO
elif menu == "Votar":
    if "eleitor_id" not in st.session_state:
        st.warning("⚠️ Faça login primeiro!")
    else:
        st.subheader("🗳️ Votação")
        eleicoes = get_eleicoes()
        if not eleicoes:
            st.info("Nenhuma eleição ativa.")
        else:
            for e in eleicoes:
                eleicao_id, titulo, data_inicio = e
                st.write(f"### {titulo}")
                candidatos = get_candidatos(eleicao_id)

                if not candidatos:
                    st.info("Nenhum candidato cadastrado.")
                    continue

                key_radio = f"eleicao_{eleicao_id}"
                escolhido = st.radio("Escolha seu candidato:", [f"{c[0]} - {c[1]}" for c in candidatos], key=key_radio)

                if st.button(f"Confirmar Voto em {titulo}", key=f"btn_{eleicao_id}"):
                    candidato_id = int(escolhido.split(" - ")[0])
                    sucesso, msg = registrar_voto(st.session_state["eleitor_id"], eleicao_id, candidato_id)
                    if sucesso:
                        st.success(msg)
                    else:
                        st.error(msg)
                    st.experimental_rerun()

# RESULTADOS
elif menu == "Resultados":
    st.subheader("📊 Resultados das Eleições")
    eleicoes = get_eleicoes()
    if not eleicoes:
        st.info("Nenhuma eleição ativa.")
    else:
        for e in eleicoes:
            eleicao_id, titulo, data_inicio = e
            st.write(f"### {titulo}")
            resultados, msg = get_resultados(eleicao_id, data_inicio)
