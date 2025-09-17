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

# --- Configurações ---
MIN_VOTOS = 2
TEMPO_LIMITE_MIN = 30  # minutos

# --- Funções auxiliares ---
def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()

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
    df = pd.DataFrame(rows, columns=["id","nome","ativa"])
    df['ativa'] = df['ativa'].astype(str).str.upper()
    return df

def carregar_candidatos():
    cur.execute("SELECT eleicao_id, nome FROM candidatos;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["eleicao_id","nome"])

def carregar_votos():
    cur.execute("SELECT id, eleicao_id, token_hash, vote_hash, datahora FROM votos;")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["id","eleicao_id","token_hash","vote_hash","datahora"])
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

active_elections = eleicoes[eleicoes['ativa'] == "TRUE"]

# --- Inicializar session_state ---
if "token" not in st.session_state:
    st.session_state["token"] = None
if "eleicao_index" not in st.session_state:
    st.session_state["eleicao_index"] = 0
if "eleicoes_pendentes" not in st.session_state:
    st.session_state["eleicoes_pendentes"] = []

# --- Streamlit UI ---
st.title("🗳️ Sistema de Votação Senge-PR (Supabase)")

# --- Entrada do eleitor ---
st.subheader("Identificação do Eleitor")
nome = st.text_input("Nome completo")
crea = st.text_input("Número do CREA")

if nome and crea:
    # --- Eleições pendentes ---
    if not st.session_state["eleicoes_pendentes"]:
        pendentes = []
        for idx, row in active_elections.iterrows():
            eleicao_id = row['id']
            cur.execute(
                "SELECT 1 FROM votos WHERE eleicao_id=%s AND nome=%s AND crea=%s",
                (eleicao_id, nome, crea)
            )
            if not cur.fetchone():
                pendentes.append(row)
        st.session_state["eleicoes_pendentes"] = pendentes

    total_eleicoes = len(active_elections)
    votadas = total_eleicoes - len(st.session_state["eleicoes_pendentes"])
    st.progress(votadas / total_eleicoes if total_eleicoes > 0 else 1.0)
    st.write(f"Eleições votadas: {votadas} / {total_eleicoes}")

    if st.session_state["eleicoes_pendentes"]:
        # Pega eleição atual
        eleicao = st.session_state["eleicoes_pendentes"][st.session_state["eleicao_index"]]
        eleicao_id = eleicao['id']
        st.info(f"Próxima eleição: **{eleicao['nome']}**")

        # --- Gerar token ---
        if not st.session_state["token"]:
            if st.button("Gerar Token"):
                token = secrets.token_urlsafe(16)
                token_hash = sha256(token)
                try:
                    cur.execute(
                        "INSERT INTO votos (eleicao_id, token_hash, vote_hash, datahora) VALUES (%s,%s,%s,%s)",
                        (eleicao_id, token_hash, '', datetime.utcnow())
                    )
                    conn.commit()
                    st.session_state["token"] = token
                    st.success("✅ Seu token foi gerado (guarde com segurança, será descartado após o voto):")
                    st.code(token)
                except Exception as e:
                    st.error(f"Erro ao registrar token: {e}")

        # --- Registrar voto ---
        if st.session_state["token"]:
            st.subheader("Registrar voto")
            candidatos_eleicao = candidatos[candidatos['eleicao_id']==eleicao_id]['nome'].tolist()
            if candidatos_eleicao:
                candidato = st.radio("Escolha seu candidato:", candidatos_eleicao)
                if st.button("Confirmar Voto"):
                    token_h = sha256(st.session_state["token"])
                    vote_hash = sha256(token_h + candidato + secrets.token_hex(8))
                    try:
                        # registra voto anonimamente
                        cur.execute(
                            "INSERT INTO eleitores (datahora, eleicao_id, candidato, token_hash, vote_hash) VALUES (%s,%s,%s,%s,%s)",
                            (datetime.utcnow(), eleicao_id, candidato, token_h, vote_hash)
                        )
                        # atualiza tabela votos para marcar token como usado
                        cur.execute(
                            "UPDATE votos SET vote_hash=%s WHERE token_hash=%s",
                            (vote_hash, token_h)
                        )
                        conn.commit()
                        st.success(f"✅ Voto registrado com sucesso para **{candidato}**!")
                        st.info("O token foi descartado após o voto.")
                        st.session_state["token"] = None
                        # avança para próxima eleição
                        if st.session_state["eleicao_index"] + 1 < len(st.session_state["eleicoes_pendentes"]):
                            st.session_state["eleicao_index"] += 1
                        else:
                            st.session_state["eleicoes_pendentes"] = []
                            st.success("✅ Você já votou em todas as eleições ativas!")
                        # recarrega votos e eleitores
                        votos = carregar_votos()
                        eleitores = carregar_eleitores()
                        st.experimental_rerun_flag = True
                    except Exception as e:
                        st.error(f"Erro ao registrar voto: {e}")
            else:
                st.warning("Nenhum candidato cadastrado para esta eleição.")
    else:
        st.success("✅ Você já votou em todas as eleições ativas!")
else:
    st.info("Preencha seu nome e número do CREA para continuar.")

# --- Resultados anonimizados ---
st.title("🏆 Resultados das Eleições (anonimizados)")
for idx, row in active_elections.iterrows():
    eleicao_id = row['id']
    votos_eleicao = eleitores[eleitores['eleicao_id']==eleicao_id]

    st.subheader(f"{row['nome']}")
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

# --- Auditoria opcional (não revela candidatos) ---
if st.checkbox("🔎 Ver auditoria de tokens"):
    st.dataframe(votos[['eleicao_id','token_hash','vote_hash','datahora']])
