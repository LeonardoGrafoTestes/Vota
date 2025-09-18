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
    df = pd.DataFrame(rows, columns=["id", "nome", "ativa"])
    df['ativa'] = df['ativa'].astype(str).str.upper()
    return df[df['ativa'] == "TRUE"]

def carregar_candidatos():
    cur.execute("SELECT eleicao_id, nome FROM candidatos;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["eleicao_id", "nome"])

def carregar_votos():
    cur.execute("SELECT id, eleicao_id, token_hash, datahora, crea FROM votos;")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["id","eleicao_id","token_hash","datahora","crea"])
    df['datahora'] = pd.to_datetime(df['datahora'], errors='coerce')
    return df

def carregar_eleitores():
    cur.execute("SELECT id, datahora, eleicao_id, candidato, token_hash, vote_hash FROM eleitores;")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["id","datahora","eleicao_id","candidato","token_hash","vote_hash"])
    df['datahora'] = pd.to_datetime(df['datahora'], errors='coerce')
    return df

# --- Carregar dados ---
eleicoes = carregar_eleicoes()
candidatos = carregar_candidatos()
votos = carregar_votos()
eleitores = carregar_eleitores()

# --- Streamlit UI ---
st.title("🗳 Sistema de Votação Senge-PR")

# --- Login inicial ---
if "logged_in" not in st.session_state:
    st.subheader("Login do Eleitor")
    nome_input = st.text_input("Nome completo")
    crea_input = st.text_input("Número do CREA")
    if st.button("Entrar"):
        if nome_input.strip() == "" or crea_input.strip() == "":
            st.error("Preencha ambos os campos para continuar.")
        else:
            st.session_state["nome"] = nome_input.strip()
            st.session_state["crea"] = crea_input.strip()
            st.session_state["logged_in"] = True

# --- Fluxo de votação ---
if st.session_state.get("logged_in"):
    nome = st.session_state["nome"]
    crea = st.session_state["crea"]

    st.info(f"Eleitor: **{nome}** | CREA: **{crea}**")

    st.subheader("Registrar votos em todas as eleições ativas")

    votos_atuais = {}  # guarda o candidato escolhido por eleição nesta sessão

    # --- Loop por todas as eleições ---
    for idx, eleicao in eleicoes.iterrows():
        eleicao_id = eleicao['id']
        st.markdown(f"### {eleicao['nome']}")

        # Atualiza votos do banco antes de exibir
        votos = carregar_votos()

        if ((votos['crea'] == crea) & (votos['eleicao_id'] == eleicao_id)).any():
            st.success("✅ Já votou nesta eleição")
        else:
            candidatos_eleicao = candidatos[candidatos['eleicao_id']==eleicao_id]['nome'].tolist()
            if candidatos_eleicao:
                escolha = st.radio(f"Escolha seu candidato para {eleicao['nome']}:", candidatos_eleicao, key=f"eleicao_{eleicao_id}")
                votos_atuais[eleicao_id] = escolha
            else:
                st.warning("Nenhum candidato cadastrado para esta eleição.")

    # --- Botão para confirmar todos os votos ---
    if st.button("Confirmar todos os votos"):
        if not votos_atuais:
            st.warning("Não há votos para registrar.")
        else:
            for eleicao_id, candidato in votos_atuais.items():
                # Verifica novamente se já votou para evitar duplicidade
                votos = carregar_votos()
                if ((votos['crea'] == crea) & (votos['eleicao_id'] == eleicao_id)).any():
                    st.warning(f"Você já votou na eleição {eleicao_id}!")
                    continue

                token = secrets.token_urlsafe(16)
                token_h = sha256(token)
                vote_hash = sha256(token_h + candidato + secrets.token_hex(8))
                try:
                    cur.execute("BEGIN;")
                    cur.execute(
                        "INSERT INTO votos (nome, crea, eleicao_id, token_hash, datahora) VALUES (%s,%s,%s,%s,%s)",
                        (nome, crea, eleicao_id, token_h, datetime.utcnow())
                    )
                    cur.execute(
                        "INSERT INTO eleitores (datahora, eleicao_id, candidato, token_hash, vote_hash) VALUES (%s,%s,%s,%s,%s)",
                        (datetime.utcnow(), eleicao_id, candidato, token_h, vote_hash)
                    )
                    conn.commit()
                    st.success(f"✅ Voto registrado para **{candidato}** na eleição {eleicao['nome']}!")
                except Exception as e:
                    conn.rollback()
                    st.error(f"Erro ao registrar voto na eleição {eleicao['nome']}: {e}")

# --- Auditoria liberada somente após concluir todas as eleições ---
if st.session_state.get("logged_in"):
    votos_pendentes = [e for idx, e in eleicoes.iterrows() if not ((carregar_votos()['crea'] == crea) & (carregar_votos()['eleicao_id'] == e['id'])).any()]
    if not votos_pendentes:
        if st.checkbox("🔎 Ver auditoria de votos"):
            st.dataframe(carregar_eleitores().drop(columns=['candidato']))

# --- Resultados ---
st.title("🏆 Resultados das Eleições Senge-PR")
for idx, eleicao in eleicoes.iterrows():
    eleicao_id = eleicao['id']
    votos_eleicao = carregar_eleitores()[carregar_eleitores()['eleicao_id']==eleicao_id]

    st.subheader(f"{eleicao['nome']}")
    total_votos = len(votos_eleicao)
    st.write(f"Total de votos registrados: {total_votos}")

    if total_votos >= MIN_VOTOS:
        first_vote_time = votos_eleicao['datahora'].min()
        prazo_liberacao = first_vote_time + timedelta(minutes=TEMPO_LIMITE_MIN)
        agora = datetime.utcnow()

        if agora >= prazo_liberacao:
            st.success("Resultados liberados:")
            contagem = votos_eleicao.groupby('candidato').size().reset_index(name='Votos')
            st.table(contagem)
        else:
            st.info(
                f"Resultados serão liberados após {TEMPO_LIMITE_MIN} minutos desde o primeiro voto.\n"
                f"Prazo de liberação: {prazo_liberacao.strftime('%d/%m/%Y %H:%M:%S UTC')}"
            )
    else:
        st.warning(f"Aguardando pelo menos {MIN_VOTOS} votos para exibir resultados.")
