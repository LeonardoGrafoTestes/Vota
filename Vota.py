import streamlit as st
import psycopg2
import hashlib
import os
from datetime import datetime

# Conexão com o banco de dados
def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        port=os.getenv("DB_PORT", 5432)
    )

# Função para hash
def gerar_hash(valor):
    return hashlib.sha256(valor.encode()).hexdigest()

# Carregar eleições ativas
def carregar_eleicoes():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, titulo, descricao FROM eleicoes WHERE ativa = TRUE;")
    eleicoes = cur.fetchall()
    cur.close()
    conn.close()
    return eleicoes

# Verificar se já votou em uma eleição específica
def ja_votou(crea, eleicao_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT confirmado FROM eleitores WHERE crea = %s AND eleicao_id = %s;", (crea, eleicao_id))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row and row[0]

# Registrar voto
def registrar_voto(eleicao_id, crea, candidato_id):
    try:
        conn = get_connection()
        cur = conn.cursor()

        token = f"{crea}-{datetime.now().isoformat()}"
        token_hash = gerar_hash(token)
        vote_hash = gerar_hash(f"{candidato_id}-{datetime.now().isoformat()}")

        cur.execute(
            "INSERT INTO votos (eleicao_id, token_hash, vote_hash, datahora) VALUES (%s, %s, %s, %s) RETURNING id;",
            (eleicao_id, token_hash, vote_hash, datetime.now())
        )
        voto_id = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO eleitores (eleicao_id, crea, confirmado) VALUES (%s, %s, %s) ON CONFLICT (eleicao_id, crea) DO UPDATE SET confirmado = EXCLUDED.confirmado;",
            (eleicao_id, crea, True)
        )

        conn.commit()
        cur.close()
        conn.close()
        return True, token
    except Exception as e:
        return False, str(e)

# Interface Streamlit
st.title("🗳️ Sistema de Votação")

if "crea" not in st.session_state:
    st.session_state.crea = ""

# Login simples com CREA
if not st.session_state.crea:
    crea_input = st.text_input("Digite seu CREA para iniciar:")
    if st.button("Entrar"):
        if crea_input.strip():
            st.session_state.crea = crea_input.strip()
            st.rerun()

else:
    st.write(f"👤 Bem-vindo, CREA: **{st.session_state.crea}**")

    eleicoes = carregar_eleicoes()

    if not eleicoes:
        st.info("Nenhuma eleição disponível no momento.")
    else:
        for eleicao in eleicoes:
            eleicao_id, titulo, descricao = eleicao
            st.subheader(f"{titulo}")
            st.caption(descricao)

            if ja_votou(st.session_state.crea, eleicao_id):
                st.success("✅ Voto já registrado e confirmado nesta eleição.")
            else:
                candidato = st.text_input(f"Digite o nome do candidato para **{titulo}**:", key=f"cand_{eleicao_id}")
                if st.button(f"Confirmar voto em {titulo}", key=f"btn_{eleicao_id}"):
                    if candidato.strip():
                        sucesso, msg = registrar_voto(eleicao_id, st.session_state.crea, candidato.strip())
                        if sucesso:
                            st.success("✅ Voto registrado com sucesso! Seu voto foi confirmado.")
                            st.rerun()
                        else:
                            st.error(f"Erro ao registrar voto: {msg}")
                    else:
                        st.warning("Digite o nome do candidato antes de confirmar.")

    if st.button("Sair"):
        st.session_state.crea = ""
        st.rerun()
