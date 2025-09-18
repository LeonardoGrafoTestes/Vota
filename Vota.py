import streamlit as st
import psycopg2
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import pandas as pd

# --- Carregar variáveis do .env ---
load_dotenv()
HOST = os.getenv("SUPABASE_HOST")
DBNAME = os.getenv("SUPABASE_DB")
USER = os.getenv("SUPABASE_USER")
PASSWORD = os.getenv("SUPABASE_PASSWORD")
PORT = os.getenv("SUPABASE_PORT")

# --- Configurações ---
MIN_VOTOS = 2
TEMPO_LIMITE_MIN = 30  # minutos

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

# --- Funções para carregar dados ---
def carregar_eleicoes():
    cur.execute("SELECT id, titulo, ativa FROM eleicoes;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["id", "titulo", "ativa"])

def carregar_candidatos():
    cur.execute("SELECT id, nome, eleicao_id FROM candidatos;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["id", "nome", "eleicao_id"])

def carregar_votos_registro():
    cur.execute("SELECT eleitor_id, eleicao_id FROM votos_registro;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["eleitor_id","eleicao_id"])

def carregar_eleitores():
    cur.execute("SELECT id, nome, crea FROM eleitores;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["id","nome","crea"])

# --- Carregar dados ---
eleitores = carregar_eleitores()
eleicoes = carregar_eleicoes()
candidatos = carregar_candidatos()
votos_registro = carregar_votos_registro()

# Eleições ativas
active_elections = eleicoes[eleicoes['ativa']==True]

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
            existing = eleitores[(eleitores['nome']==nome_input.strip()) & (eleitores['crea']==crea_input.strip())]
            if existing.empty:
                # Insere novo eleitor
                cur.execute("INSERT INTO eleitores (nome, crea) VALUES (%s,%s) RETURNING id", (nome_input.strip(), crea_input.strip()))
                eleitor_id = cur.fetchone()[0]
                conn.commit()
            else:
                eleitor_id = existing.iloc[0]['id']
            st.session_state["logged_in"] = True
            st.session_state["eleitor_id"] = eleitor_id
            st.session_state["nome"] = nome_input.strip()
            st.session_state["crea"] = crea_input.strip()
            st.experimental_rerun()

# --- Fluxo de votação ---
if st.session_state.get("logged_in"):
    eleitor_id = st.session_state["eleitor_id"]
    st.info(f"Eleitor: **{st.session_state['nome']}** | CREA: **{st.session_state['crea']}**")

    st.subheader("Registrar votos em todas as eleições ativas")
    votos_para_registrar = {}
    for _, eleicao in active_elections.iterrows():
        eleicao_id = eleicao['id']
        # Verifica se já votou nesta eleição
        if ((votos_registro['eleitor_id']==eleitor_id) & (votos_registro['eleicao_id']==eleicao_id)).any():
            st.success(f"✅ Já votou na eleição {eleicao['titulo']}")
        else:
            st.write(f"**{eleicao['titulo']}**")
            candidatos_eleicao = candidatos[candidatos['eleicao_id']==eleicao_id]
            if not candidatos_eleicao.empty:
                opcao = st.radio(f"Escolha seu candidato para {eleicao['titulo']}:", candidatos_eleicao['nome'].tolist(), key=f"eleicao_{eleicao_id}")
                votos_para_registrar[eleicao_id] = candidatos_eleicao[candidatos_eleicao['nome']==opcao].iloc[0]['id']
            else:
                st.warning("Nenhum candidato cadastrado para esta eleição.")

    if votos_para_registrar:
        if st.button("Confirmar todos os votos"):
            for eleicao_id, candidato_id in votos_para_registrar.items():
                try:
                    # Insere voto secreto
                    cur.execute(
                        "INSERT INTO votos (eleicao_id, candidato_id) VALUES (%s,%s)", 
                        (eleicao_id, candidato_id)
                    )
                    # Marca registro do eleitor
                    cur.execute(
                        "INSERT INTO votos_registro (eleitor_id, eleicao_id) VALUES (%s,%s)",
                        (eleitor_id, eleicao_id)
                    )
                    conn.commit()
                    st.success(f"✅ Voto registrado na eleição {eleicao_id}")
                except Exception as e:
                    conn.rollback()
                    st.error(f"Erro ao registrar voto na eleição {eleicao_id}: {e}")

# --- Resultados (somente contagem, sem expor eleitores) ---
st.title("🏆 Resultados das Eleições Senge-PR")
for _, eleicao in active_elections.iterrows():
    eleicao_id = eleicao['id']
    cur.execute("SELECT c.nome, COUNT(*) FROM votos v JOIN candidatos c ON v.candidato_id=c.id WHERE v.eleicao_id=%s GROUP BY c.nome", (eleicao_id,))
    resultados = cur.fetchall()
    total_votos = sum(r[1] for r in resultados)
    st.subheader(eleicao['titulo'])
    st.write(f"Total de votos registrados: {total_votos}")
    if total_votos >= MIN_VOTOS:
        st.table(pd.DataFrame(resultados, columns=["Candidato","Votos"]))
    else:
        st.warning(f"Aguardando pelo menos {MIN_VOTOS} votos para exibir resultados.")
