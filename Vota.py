import streamlit as st
import psycopg2
import secrets
import hashlib
from datetime import datetime

# --- Funções auxiliares ---
def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()

def conectar():
    return psycopg2.connect(
        host=st.secrets["db_host"],
        dbname=st.secrets["db_name"],
        user=st.secrets["db_user"],
        password=st.secrets["db_password"],
        port=st.secrets["db_port"]
    )

def ja_votou(crea, eleicao_id):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM votos WHERE crea=%s AND eleicao_id=%s", (crea, eleicao_id))
    existe = cur.fetchone() is not None
    cur.close()
    conn.close()
    return existe

def atualizar_eleicoes_pendentes(crea):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("SELECT id, titulo FROM eleicoes ORDER BY id")
    todas = cur.fetchall()
    pendentes = []
    for e in todas:
        if not ja_votou(crea, e[0]):
            pendentes.append(e)
    cur.close()
    conn.close()
    return pendentes

# --- Login ---
st.title("🗳️ Sistema de Votação")

if "login_ok" not in st.session_state:
    st.session_state["login_ok"] = False

if not st.session_state["login_ok"]:
    with st.form("login_form"):
        nome = st.text_input("Digite seu nome completo")
        crea = st.text_input("Digite seu CREA")
        if st.form_submit_button("Entrar"):
            if nome.strip() == "" or crea.strip() == "":
                st.error("Preencha nome e CREA.")
            else:
                st.session_state["nome"] = nome.strip()
                st.session_state["crea"] = crea.strip()
                st.session_state["login_ok"] = True
                st.session_state["eleicao_idx"] = 0
                st.rerun()

else:
    nome = st.session_state["nome"]
    crea = st.session_state["crea"]

    st.sidebar.success(f"Logado como: {nome} ({crea})")

    # Buscar eleições pendentes
    eleicoes_pendentes = atualizar_eleicoes_pendentes(crea)

    if len(eleicoes_pendentes) == 0:
        st.success("✅ Você já votou em todas as eleições!")
    else:
        eleicao_id, titulo = eleicoes_pendentes[st.session_state["eleicao_idx"]]
        st.header(f"🗳️ Eleição: {titulo}")

        # Buscar candidatos
        conn = conectar()
        cur = conn.cursor()
        cur.execute("SELECT nome FROM candidatos WHERE eleicao_id=%s", (eleicao_id,))
        candidatos = [c[0] for c in cur.fetchall()]
        cur.close()
        conn.close()

        escolha = st.radio("Escolha seu candidato:", candidatos, key=f"candidato_{eleicao_id}")

        if st.button("Confirmar Voto"):
            candidato_escolhido = st.session_state.get(f"candidato_{eleicao_id}")
            if not candidato_escolhido:
                st.error("Selecione um candidato antes de confirmar.")
            else:
                token_h = sha256(secrets.token_hex(16))
                vote_hash = sha256(token_h + candidato_escolhido + secrets.token_hex(8))
                try:
                    conn = conectar()
                    cur = conn.cursor()

                    # Registra voto em votos
                    cur.execute(
                        "INSERT INTO votos (nome, crea, eleicao_id, token_hash, datahora) VALUES (%s,%s,%s,%s,%s)",
                        (nome, crea, eleicao_id, token_h, datetime.utcnow())
                    )

                    # Registra auditoria em eleitores
                    cur.execute(
                        "INSERT INTO eleitores (datahora, eleicao_id, candidato, token_hash, vote_hash) VALUES (%s,%s,%s,%s,%s)",
                        (datetime.utcnow(), eleicao_id, candidato_escolhido, token_h, vote_hash)
                    )

                    conn.commit()
                    cur.close()
                    conn.close()

                    st.success(f"✅ Voto registrado com sucesso para **{candidato_escolhido}**!")
                    st.info("O token foi descartado após o voto.")

                    # limpar seleção
                    del st.session_state[f"candidato_{eleicao_id}"]

                    # Atualizar lista de pendentes
                    eleicoes_pendentes = atualizar_eleicoes_pendentes(crea)

                    if len(eleicoes_pendentes) > 0:
                        st.session_state["eleicao_idx"] = 0
                        st.rerun()
                    else:
                        st.success("🎉 Você já votou em todas as eleições ativas!")

                except psycopg2.IntegrityError:
                    conn.rollback()
                    st.error("⚠️ Você já votou nesta eleição!")
                except Exception as e:
                    conn.rollback()
                    st.error(f"Erro ao registrar voto: {e}")
