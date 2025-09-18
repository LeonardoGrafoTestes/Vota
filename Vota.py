import streamlit as st
import hashlib, secrets
import psycopg2
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
import pandas as pd

# --- Carregar variáveis do .env ---
load_dotenv()
HOST = os.getenv("SUPABASE_HOST")
PORT = os.getenv("SUPABASE_PORT")
DBNAME = os.getenv("SUPABASE_DB")
USER = os.getenv("SUPABASE_USER")
PASSWORD = os.getenv("SUPABASE_PASSWORD")

# --- Função auxiliar ---
def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()

# --- Configurações ---
MIN_VOTOS = 2
TEMPO_LIMITE_MIN = 30  # minutos para liberar resultados

# --- Conexão com Supabase ---
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

# --- Funções para carregar dados ---
def carregar_eleitores():
    cur.execute("SELECT * FROM eleitores;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["id","nome","crea","email","data_cadastro"])

def carregar_eleicoes():
    cur.execute("SELECT * FROM eleicoes WHERE ativa=true;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["id","titulo","descricao","ativa","data_inicio","data_fim"])

def carregar_candidatos():
    cur.execute("SELECT * FROM candidatos;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["id","nome","eleicao_id"])

def carregar_votos():
    cur.execute("SELECT * FROM votos;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["id","eleicao_id","candidato_id","datahora"])

def carregar_votos_registro():
    cur.execute("SELECT * FROM votos_registro;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["id","eleitor_id","eleicao_id","datahora"])

# --- Carregar dados ---
eleitores = carregar_eleitores()
eleicoes = carregar_eleicoes()
candidatos = carregar_candidatos()
votos = carregar_votos()
votos_registro = carregar_votos_registro()

# --- Streamlit UI ---
st.title("🗳 Sistema de Votação Senge-PR")

# --- Login do eleitor ---
if "logged_in" not in st.session_state:
    st.subheader("Login do Eleitor")
    nome_input = st.text_input("Nome completo")
    crea_input = st.text_input("Número do CREA")
    if st.button("Entrar"):
        if nome_input.strip() == "" or crea_input.strip() == "":
            st.error("Preencha ambos os campos.")
        else:
            # Verifica se já existe o eleitor
            eleitor = eleitores[(eleitores['nome']==nome_input.strip()) & (eleitores['crea']==crea_input.strip())]
            if eleitor.empty:
                # cadastra novo eleitor
                cur.execute(
                    "INSERT INTO eleitores (nome, crea) VALUES (%s,%s) RETURNING id;",
                    (nome_input.strip(), crea_input.strip())
                )
                conn.commit()
                eleitor_id = cur.fetchone()[0]
            else:
                eleitor_id = int(eleitor['id'].values[0])

            st.session_state["logged_in"] = True
            st.session_state["nome"] = nome_input.strip()
            st.session_state["crea"] = crea_input.strip()
            st.session_state["eleitor_id"] = eleitor_id

# --- Fluxo de votação ---
if st.session_state.get("logged_in"):
    st.info(f"Eleitor: **{st.session_state['nome']}** | CREA: **{st.session_state['crea']}**")
    eleitor_id = st.session_state["eleitor_id"]

    st.subheader("Registrar votos em todas as eleições ativas")
    votos_para_registrar = []
    for idx, eleicao in eleicoes.iterrows():
        # Verifica se já votou
        if not ((votos_registro['eleitor_id']==eleitor_id) & (votos_registro['eleicao_id']==eleicao['id'])).any():
            st.markdown(f"### {eleicao['titulo']}")
            candidatos_eleicao = candidatos[candidatos['eleicao_id']==eleicao['id']]
            escolha = st.radio(f"Escolha seu candidato para {eleicao['titulo']}:", candidatos_eleicao['nome'].tolist(), key=f"eleicao_{eleicao['id']}")
            votos_para_registrar.append((eleicao['id'], escolha))
        else:
            st.success(f"✅ Já votou nesta eleição: {eleicao['titulo']}")

    if votos_para_registrar:
        if st.button("Confirmar todos os votos"):
            try:
                for eleicao_id, candidato_nome in votos_para_registrar:
                    candidato_id = int(candidatos[(candidatos['eleicao_id']==eleicao_id) & (candidatos['nome']==candidato_nome)]['id'].values[0])
                    # Inserir voto secreto
                    cur.execute(
                        "INSERT INTO votos (eleicao_id, candidato_id) VALUES (%s,%s);",
                        (eleicao_id, candidato_id)
                    )
                    # Registrar que o eleitor votou
                    cur.execute(
                        "INSERT INTO votos_registro (eleitor_id, eleicao_id) VALUES (%s,%s);",
                        (eleitor_id, eleicao_id)
                    )
                conn.commit()
                st.success("✅ Todos os votos foram registrados com sucesso!")
                # Atualiza tabelas
                votos = carregar_votos()
                votos_registro = carregar_votos_registro()
            except Exception as e:
                conn.rollback()
                st.error(f"Erro ao registrar votos: {e}")

# --- Resultados ---
st.title("🏆 Resultados das Eleições Senge-PR")
for idx, eleicao in eleicoes.iterrows():
    st.subheader(f"{eleicao['titulo']}")
    votos_eleicao = votos[votos['eleicao_id']==eleicao['id']]
    total_votos = len(votos_eleicao)
    st.write(f"Total de votos registrados: {total_votos}")
    if total_votos >= MIN_VOTOS:
        first_vote_time = votos_eleicao['datahora'].min()
        prazo_liberacao = first_vote_time + timedelta(minutes=TEMPO_LIMITE_MIN)
        agora = datetime.utcnow()
        if agora >= prazo_liberacao:
            contagem = votos_eleicao.merge(candidatos, left_on='candidato_id', right_on='id')
            contagem = contagem.groupby('nome').size().reset_index(name='Votos')
            st.table(contagem)
        else:
            st.info(f"Resultados serão liberados após {TEMPO_LIMITE_MIN} minutos desde o primeiro voto.")
    else:
        st.warning(f"Aguardando pelo menos {MIN_VOTOS} votos para exibir resultados.")
