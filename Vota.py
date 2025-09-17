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
DBNAME = os.getenv("SUPABASE_DB")
USER = os.getenv("SUPABASE_USER")
PASSWORD = os.getenv("SUPABASE_PASSWORD")
PORT = os.getenv("SUPABASE_PORT")

def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()

MIN_VOTOS = 2
TEMPO_LIMITE_MIN = 30

# --- Conexão ---
try:
    conn = psycopg2.connect(host=HOST, dbname=DBNAME, user=USER, password=PASSWORD, port=PORT)
    cur = conn.cursor()
except Exception as e:
    st.error(f"Erro ao conectar ao banco: {e}")
    st.stop()

# --- Carregar dados ---
def carregar_eleicoes():
    cur.execute("SELECT id, nome, ativa FROM eleicoes;")
    return pd.DataFrame(cur.fetchall(), columns=["ID","Nome","Ativa"])

def carregar_candidatos():
    cur.execute("SELECT eleicao_id, nome FROM candidatos;")
    return pd.DataFrame(cur.fetchall(), columns=["Eleicao_ID","Nome"])

def carregar_votos():
    cur.execute("SELECT eleicao_id, token_hash, datahora FROM votos;")
    df = pd.DataFrame(cur.fetchall(), columns=["Eleicao_ID","Token_Hash","DataHora"])
    df['DataHora'] = pd.to_datetime(df['DataHora'], errors='coerce')
    return df

def carregar_eleitores():
    cur.execute("SELECT datahora, eleicao_id, candidato, token_hash, vote_hash FROM eleitores;")
    df = pd.DataFrame(cur.fetchall(), columns=["DataHora","Eleicao_ID","Candidato","Token_Hash","Vote_Hash"])
    df['DataHora'] = pd.to_datetime(df['DataHora'], errors='coerce')
    return df

eleicoes = carregar_eleicoes()
candidatos = carregar_candidatos()
votos = carregar_votos()
eleitores = carregar_eleitores()
eleicoes['Ativa'] = eleicoes['Ativa'].astype(str).str.upper()
active_elections = eleicoes[eleicoes['Ativa']=="TRUE"]

st.title("🗳️ Sistema de Votação Senge-PR")

# --- Identificação ---
st.subheader("Identificação do Eleitor")
nome = st.text_input("Nome completo")
crea = st.text_input("Número do CREA")

if nome and crea:
    # --- Eleições pendentes ---
    eleicoes_pendentes = []
    for idx, row in active_elections.iterrows():
        eleicao_id = row['ID']
        # Verifica se CREA já votou nessa eleição
        cur.execute("SELECT 1 FROM votos v JOIN eleitores e ON v.token_hash=e.token_hash WHERE v.eleicao_id=%s AND v.token_hash IN (SELECT token_hash FROM votos WHERE eleicao_id=%s) LIMIT 1;", (eleicao_id, eleicao_id))
        votou = cur.fetchone()
        if not votou:
            eleicoes_pendentes.append(row)

    total_eleicoes = len(active_elections)
    votadas = total_eleicoes - len(eleicoes_pendentes)
    st.progress(votadas / total_eleicoes if total_eleicoes > 0 else 1.0)
    st.write(f"Eleições votadas: {votadas} / {total_eleicoes}")

    if eleicoes_pendentes:
        eleicao = eleicoes_pendentes[0]
        eleicao_id = eleicao['ID']
        st.info(f"Próxima eleição: **{eleicao['Nome']}**")

        # --- Gerar token ---
        if "token" not in st.session_state:
            if st.button("Gerar Token"):
                token = secrets.token_urlsafe(16)
                token_hash = sha256(token)
                # Inserir token no banco
                cur.execute("INSERT INTO votos (eleicao_id, token_hash, datahora) VALUES (%s,%s,%s)", (eleicao_id, token_hash, datetime.utcnow()))
                conn.commit()
                st.session_state["token"] = token
                st.success("✅ Token gerado. Será descartado após o voto.")
                st.code(token)
                votos = carregar_votos()  # recarregar

        # --- Registrar voto ---
        if "token" in st.session_state:
            st.subheader("Registrar voto")
            candidatos_eleicao = candidatos[candidatos['Eleicao_ID']==eleicao_id]['Nome'].tolist()
            if candidatos_eleicao:
                candidato = st.radio("Escolha seu candidato:", candidatos_eleicao)
                if st.button("Confirmar Voto"):
                    token_h = sha256(st.session_state["token"])
                    vote_hash = sha256(token_h + candidato + secrets.token_hex(8))
                    cur.execute("INSERT INTO eleitores (datahora, eleicao_id, candidato, token_hash, vote_hash) VALUES (%s,%s,%s,%s,%s)",
                                (datetime.utcnow(), eleicao_id, candidato, token_h, vote_hash))
                    conn.commit()
                    st.success(f"✅ Voto confirmado para **{candidato}**!")
                    st.write("Hash do voto (anonimizado):", vote_hash)
                    del st.session_state["token"]
                    votos = carregar_votos()
                    eleitores = carregar_eleitores()
                    st.experimental_rerun()
            else:
                st.warning("Nenhum candidato cadastrado.")
    else:
        st.success("✅ Você já votou em todas as eleições ativas!")
else:
    st.info("Preencha nome e CREA.")

# --- Resultados ---
st.title("🏆 Resultados")
for idx, row in active_elections.iterrows():
    eleicao_id = row['ID']
    votos_eleicao = eleitores[eleitores['Eleicao_ID']==eleicao_id]
    st.subheader(f"{row['Nome']}")
    total_votos = len(votos_eleicao)
    st.write(f"Total de votos: {total_votos}")

    if total_votos >= MIN_VOTOS:
        first_vote_time = votos_eleicao['DataHora'].min()
        prazo_liberacao = first_vote_time + timedelta(minutes=TEMPO_LIMITE_MIN)
        agora = datetime.utcnow()
        if agora >= prazo_liberacao:
            st.success("Resultados liberados:")
            contagem = votos_eleicao.groupby('Candidato').size().reset_index(name='Votos')
            st.table(contagem)
        else:
            st.info(f"Resultados liberados após {TEMPO_LIMITE_MIN} minutos do primeiro voto.")
    else:
        st.warning(f"Aguardando pelo menos {MIN_VOTOS} votos.")
