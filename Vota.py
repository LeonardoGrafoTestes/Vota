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
    cur.execute("SELECT eleicao_id, token_hash, vote_hash, datahora FROM votos;")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["Eleicao_ID","Token_Hash","Vote_Hash","DataHora"])
    df['DataHora'] = pd.to_datetime(df['DataHora'], errors='coerce')
    return df

def carregar_eleitores():
    cur.execute("SELECT datahora, eleicao_id, candidato, token_hash, vote_hash FROM eleitores;")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["DataHora","Eleicao_ID","Candidato","Token_Hash","Vote_Hash"])
    df['DataHora'] = pd.to_datetime(df['DataHora'], errors='coerce')
    return df

# --- Carregar dados ---
eleicoes = carregar_eleicoes()
candidatos = carregar_candidatos()
votos = carregar_votos()
eleitores = carregar_eleitores()

active_elections = eleicoes[eleicoes['Ativa']=="TRUE"]

# --- Streamlit UI ---
st.title("🗳️ Sistema de Votação CREA (Supabase)")

# --- Entrada do eleitor ---
st.subheader("Identificação do Eleitor")
nome = st.text_input("Nome completo")
crea = st.text_input("Número do CREA")

if nome and crea:
    # --- Eleições pendentes ---
    eleicoes_pendentes = []
    for _, row in active_elections.iterrows():
        eleicao_id = row['ID']
        # verifica se já votou nessa eleição
        cur.execute("SELECT COUNT(*) FROM votos WHERE eleicao_id=%s AND token_hash IN (SELECT token_hash FROM votos WHERE crea=%s);", (eleicao_id, crea))
        if cur.fetchone()[0] == 0:
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
                try:
                    cur.execute(
                        "INSERT INTO votos (eleicao_id, token_hash, vote_hash, datahora, nome, crea) VALUES (%s,%s,%s,%s,%s,%s)",
                        (eleicao_id, token_hash, None, datetime.utcnow(), nome, crea)
                    )
                    conn.commit()
                    st.session_state["token"] = token
                    st.success("✅ Seu token foi gerado (guarde com segurança):")
                    st.code(token)
                    votos = carregar_votos()  # atualiza
                except Exception as e:
                    st.error(f"Erro ao registrar token: {e}")

        # --- Registrar voto ---
        if "token" in st.session_state:
            st.subheader("Registrar voto")
            candidatos_eleicao = candidatos[candidatos['Eleicao_ID']==eleicao_id]['Nome'].tolist()

            if candidatos_eleicao:
                candidato = st.radio("Escolha seu candidato:", candidatos_eleicao)
                if st.button("Confirmar Voto"):
                    token_h = sha256(st.session_state["token"])
                    vote_hash = sha256(token_h + candidato + secrets.token_hex(8))
                    try:
                        cur.execute(
                            "INSERT INTO eleitores (datahora, eleicao_id, candidato, token_hash, vote_hash) VALUES (%s,%s,%s,%s,%s)",
                            (datetime.utcnow(), eleicao_id, candidato, token_h, vote_hash)
                        )
                        # atualizar vote_hash na tabela votos
                        cur.execute(
                            "UPDATE votos SET vote_hash=%s WHERE token_hash=%s",
                            (vote_hash, token_h)
                        )
                        conn.commit()
                        st.success(f"✅ Voto registrado com sucesso para **{candidato}**!")
                        st.info("⚠️ O token foi descartado após o voto e não pode ser reutilizado.")
                        del st.session_state["token"]
                        votos = carregar_votos()
                        eleitores = carregar_eleitores()
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Erro ao registrar voto: {e}")
            else:
                st.warning("Nenhum candidato cadastrado para esta eleição.")
    else:
        st.success("✅ Você já votou em todas as eleições ativas!")
else:
    st.info("Preencha seu nome e número do CREA para continuar.")

# --- Resultados ---
st.title("🏆 Resultados das Eleições CREA")
for _, row in active_elections.iterrows():
    eleicao_id = row['ID']
    votos_eleicao = votos[votos['Eleicao_ID']==eleicao_id]

    st.subheader(f"{row['Nome']}")
    total_votos = len(votos_eleicao)
    st.write(f"Total de votos registrados: {total_votos}")

    if total_votos >= MIN_VOTOS:
        first_vote_time = votos_eleicao['DataHora'].min()
        prazo_liberacao = first_vote_time + timedelta(minutes=TEMPO_LIMITE_MIN)
        agora = datetime.utcnow()

        if agora >= prazo_liberacao:
            st.success("Resultados liberados:")
            contagem = eleitores[eleitores['Eleicao_ID']==eleicao_id].groupby('Candidato').size().reset_index(name='Votos')
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
