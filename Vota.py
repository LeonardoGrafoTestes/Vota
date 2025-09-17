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

# --- Funções auxiliares ---
def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()

# --- Configurações ---
MIN_VOTOS = 2
TEMPO_LIMITE_MIN = 30  # minutos

# --- Conexão com Supabase ---
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
    st.error(f"Erro ao conectar ao Supabase: {e}")
    st.stop()

# --- Funções para carregar dados ---
def carregar_eleicoes():
    cur.execute("SELECT id, nome, ativa FROM eleicoes;")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["ID","Nome","Ativa"])
    df['Ativa'] = df['Ativa'].astype(str).str.upper()
    return df

def carregar_candidatos():
    cur.execute("SELECT eleicao_id, nome FROM candidatos;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["Eleicao_ID","Nome"])

def carregar_votos():
    cur.execute("SELECT crea, token_hash, eleicao_id, datahora FROM votos;")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["CREA","Token_Hash","Eleicao_ID","DataHora"])
    df['DataHora'] = pd.to_datetime(df['DataHora'], errors='coerce')
    return df

def carregar_eleitores():
    cur.execute("SELECT eleicao_id, candidato, token_hash, vote_hash, datahora FROM eleitores;")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["Eleicao_ID","Candidato","Token_Hash","Vote_Hash","DataHora"])
    df['DataHora'] = pd.to_datetime(df['DataHora'], errors='coerce')
    return df

# --- Carregar dados ---
eleicoes = carregar_eleicoes()
candidatos = carregar_candidatos()
votos = carregar_votos()
eleitores = carregar_eleitores()

active_elections = eleicoes[eleicoes['Ativa']=="TRUE"]

# --- Streamlit UI ---
st.title("🗳️ Sistema de Votação Senge-PR (Supabase)")

# --- Entrada do eleitor ---
st.subheader("Identificação do Eleitor")
nome = st.text_input("Nome completo")
crea = st.text_input("Número do CREA")

if nome and crea:
    # Verificar tokens ativos do CREA para eleições ativas
    tokens_ativos = votos[(votos['CREA']==crea) & (votos['Eleicao_ID'].isin(active_elections['ID']))]

    if not tokens_ativos.empty:
        st.warning("⚠️ Você já gerou token para esta eleição. Complete o voto antes de gerar outro token.")
    else:
        # --- Gerar token ---
        if "token" not in st.session_state:
            if st.button("Gerar Token"):
                if not active_elections.empty:
                    eleicao = active_elections.iloc[0]
                    eleicao_id = eleicao['ID']
                    token = secrets.token_urlsafe(16)
                    token_hash = sha256(token)

                    # Inserir token no banco de dados (tabela Votos)
                    try:
                        cur.execute(
                            "INSERT INTO votos (crea, token_hash, eleicao_id, datahora) VALUES (%s,%s,%s,%s);",
                            (crea, token_hash, eleicao_id, datetime.utcnow())
                        )
                        conn.commit()
                        st.session_state["token"] = token
                        st.success("✅ Seu token foi gerado (guarde com segurança):")
                        st.code(token)
                        # Recarregar votos
                        votos = carregar_votos()
                    except Exception as e:
                        st.error(f"Erro ao registrar token: {e}")
                else:
                    st.warning("Não há eleições ativas no momento.")
        else:
            st.info("Token já gerado, prossiga para registrar seu voto.")

    # --- Registrar voto ---
    if "token" in st.session_state:
        eleicao = active_elections.iloc[0]
        eleicao_id = eleicao['ID']
        candidatos_eleicao = candidatos[candidatos['Eleicao_ID']==eleicao_id]['Nome'].tolist()

        st.subheader(f"Registrar voto para: {eleicao['Nome']}")
        if candidatos_eleicao:
            candidato = st.radio("Escolha seu candidato:", candidatos_eleicao)
            if st.button("Confirmar Voto"):
                token_h = sha256(st.session_state["token"])
                vote_hash = sha256(token_h + candidato + secrets.token_hex(8))
                try:
                    cur.execute(
                        "INSERT INTO eleitores (eleicao_id, candidato, token_hash, vote_hash, datahora) VALUES (%s,%s,%s,%s,%s);",
                        (eleicao_id, candidato, token_h, vote_hash, datetime.utcnow())
                    )
                    conn.commit()
                    st.success(f"✅ Voto registrado com sucesso para **{candidato}**!")
                    st.info("⚠️ Seu token foi descartado após o voto.")
                    # Limpar token
                    del st.session_state["token"]
                    # Recarregar votos e eleitores
                    votos = carregar_votos()
                    eleitores = carregar_eleitores()
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Erro ao registrar voto: {e}")
        else:
            st.warning("Nenhum candidato cadastrado para esta eleição.")
else:
    st.info("Preencha seu nome e número do CREA para continuar.")

# --- Resultados ---
st.title("🏆 Resultados das Eleições Senge-PR")
for idx, row in active_elections.iterrows():
    eleicao_id = row['ID']
    votos_eleicao = eleitores[eleitores['Eleicao_ID']==eleicao_id]

    st.subheader(f"{row['Nome']}")
    total_votos = len(votos_eleicao)
    st.write(f"Total de votos registrados: {total_votos}")

    if total_votos >= MIN_VOTOS:
        first_vote_time = votos_eleicao['DataHora'].min()
        prazo_liberacao = first_vote_time + timedelta(minutes=TEMPO_LIMITE_MIN)
        agora = datetime.utcnow()

        if agora >= prazo_liberacao:
            st.success("Resultados liberados:")
            contagem = votos_eleicao.groupby('Candidato').size().reset_index(name='Votos')
            st.table(contagem)
        else:
            st.info(
                f"Resultados serão liberados após {TEMPO_LIMITE_MIN} minutos desde o primeiro voto.\n"
                f"Prazo de liberação: {prazo_liberacao.strftime('%d/%m/%Y %H:%M:%S UTC')}"
            )
    else:
        st.warning(f"Aguardando pelo menos {MIN_VOTOS} votos para exibir resultados.")

# --- Auditoria opcional ---
if st.checkbox("🔎 Ver auditoria de votos"):
    st.dataframe(eleitores)
