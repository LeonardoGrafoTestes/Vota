import streamlit as st
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
import os

# --- Carregar variáveis do .env (não colocar no GitHub) ---
load_dotenv()
HOST = os.getenv("SUPABASE_HOST")
PORT = int(os.getenv("SUPABASE_PORT"))
DBNAME = os.getenv("SUPABASE_DB")
USER = os.getenv("SUPABASE_USER")
PASSWORD = os.getenv("SUPABASE_PASSWORD")

# --- Conexão com o Supabase ---
try:
    conn = psycopg2.connect(
        host=HOST,
        port=PORT,
        dbname=DBNAME,
        user=USER,
        password=PASSWORD,
        sslmode="require"
    )
    cur = conn.cursor()
except Exception as e:
    st.error(f"Erro ao conectar ao banco: {e}")
    st.stop()

# --- Streamlit UI ---
st.title("🗳 Sistema de Votação Senge-PR")

# --- Login ---
if "logged_in" not in st.session_state:
    st.subheader("Login do Eleitor")
    nome_input = st.text_input("Nome completo")
    crea_input = st.text_input("Número do CREA")
    if st.button("Entrar"):
        if not nome_input.strip() or not crea_input.strip():
            st.error("Preencha ambos os campos.")
        else:
            # Verifica se o eleitor já existe
            cur.execute("SELECT id FROM eleitores WHERE nome=%s AND crea=%s", (nome_input.strip(), crea_input.strip()))
            result = cur.fetchone()
            if result:
                st.session_state["eleitor_id"] = result[0]
            else:
                cur.execute(
                    "INSERT INTO eleitores (nome, crea) VALUES (%s, %s) RETURNING id",
                    (nome_input.strip(), crea_input.strip())
                )
                st.session_state["eleitor_id"] = cur.fetchone()[0]
                conn.commit()
            st.session_state["nome"] = nome_input.strip()
            st.session_state["crea"] = crea_input.strip()
            st.session_state["logged_in"] = True

# --- Fluxo de votação ---
if st.session_state.get("logged_in"):
    eleitor_id = st.session_state["eleitor_id"]
    st.info(f"Eleitor: **{st.session_state['nome']}** | CREA: **{st.session_state['crea']}**")

    # Carrega eleições ativas
    cur.execute("SELECT id, titulo FROM eleicoes WHERE ativa=true ORDER BY id")
    eleicoes = cur.fetchall()

    votos_para_registrar = []

    for eleicao in eleicoes:
        eleicao_id, titulo = eleicao
        # Verifica se já votou
        cur.execute("SELECT 1 FROM votos_registro WHERE eleitor_id=%s AND eleicao_id=%s", (eleitor_id, eleicao_id))
        if cur.fetchone():
            st.warning(f"✅ Você já votou na eleição {titulo}")
            continue

        # Seleção de candidato
        cur.execute("SELECT id, nome FROM candidatos WHERE eleicao_id=%s", (eleicao_id,))
        candidatos = cur.fetchall()
        if not candidatos:
            st.warning(f"Nenhum candidato cadastrado para {titulo}")
            continue

        opcoes = {str(cid): nome for cid, nome in candidatos}
        escolha = st.radio(f"Escolha seu candidato para {titulo}:", list(opcoes.values()), key=f"eleicao_{eleicao_id}")
        for cid, nome in opcoes.items():
            if nome == escolha:
                votos_para_registrar.append((eleicao_id, int(cid)))

    # Botão de confirmar todos os votos
    if votos_para_registrar and st.button("Confirmar todos os votos"):
        for eleicao_id, candidato_id in votos_para_registrar:
            # Inserir voto secreto
            cur.execute(
                "INSERT INTO votos (eleicao_id, candidato_id) VALUES (%s, %s)",
                (eleicao_id, candidato_id)
            )
            # Registrar que o eleitor votou
            cur.execute(
                "INSERT INTO votos_registro (eleitor_id, eleicao_id) VALUES (%s, %s)",
                (eleitor_id, eleicao_id)
            )
        conn.commit()
        st.success("✅ Todos os votos registrados com sucesso!")

# --- Resultados ---
st.title("🏆 Resultados das Eleições")
cur.execute("""
    SELECT e.titulo, c.nome, COUNT(v.id) as votos
    FROM votos v
    JOIN candidatos c ON v.candidato_id = c.id
    JOIN eleicoes e ON v.eleicao_id = e.id
    GROUP BY e.titulo, c.nome
    ORDER BY e.titulo, votos DESC
""")
resultados = cur.fetchall()

for titulo, nome, total in resultados:
    st.write(f"**{titulo}** - {nome}: {total} voto(s)")
