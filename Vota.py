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
    return pd.DataFrame(rows, columns=["id", "nome", "ativa"])

def carregar_candidatos():
    cur.execute("SELECT eleicao_id, nome FROM candidatos;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["eleicao_id", "nome"])

def carregar_votos():
    cur.execute("SELECT id, eleicao_id, token_hash, vote_hash, datahora FROM votos;")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["id", "eleicao_id", "token_hash", "vote_hash", "datahora"])
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

eleicoes['ativa'] = eleicoes['ativa'].astype(str).str.upper()
active_elections = eleicoes[eleicoes['ativa'] == "TRUE"]

# --- Streamlit UI ---
st.title("🗳️ Sistema de Votação Senge-PR (Supabase)")

# --- Entrada do eleitor ---
st.subheader("Identificação do Eleitor")
nome = st.text_input("Nome completo")
crea = st.text_input("Número do CREA")

if nome and crea:
    # --- Eleições pendentes ---
    eleicoes_pendentes = []
    for idx, row in active_elections.iterrows():
        eleicao_id = row['id']
        if not ((votos['token_hash'].isin(eleitores[eleitores['eleicao_id']==eleicao_id]['token_hash'])) & (votos['eleicao_id']==eleicao_id)).any():
            eleicoes_pendentes.append(row)

    total_eleicoes = len(active_elections)
    votadas = total_eleicoes - len(eleicoes_pendentes)

    # Barra de progresso
    st.progress(votadas / total_eleicoes if total_eleicoes > 0 else 1.0)
    st.write(f"Eleições votadas: {votadas} / {total_eleicoes}")

    if eleicoes_pendentes:
        eleicao = eleicoes_pendentes[0]
        eleicao_id = eleicao['id']
        st.info(f"Próxima eleição: **{eleicao['nome']}**")

        # --- Gerar token ---
        if "token" not in st.session_state or st.session_state.get("eleicao_id") != eleicao_id:
            if st.button("Gerar Token"):
                token = secrets.token_urlsafe(16)
                token_hash = sha256(token)

                # Registrar token anonimamente no banco
                try:
                    cur.execute(
                        "INSERT INTO votos (eleicao_id, token_hash, vote_hash, datahora) VALUES (%s,%s,%s,%s)",
                        (eleicao_id, token_hash, None, datetime.utcnow())
                    )
                    conn.commit()
                    st.session_state["token"] = token
                    st.session_state["eleicao_id"] = eleicao_id
                    st.success("✅ Seu token foi gerado (guarde com segurança):")
                    st.code(token)
                except Exception as e:
                    st.error(f"Erro ao registrar token: {e}")

        # --- Registrar voto ---
        if "token" in st.session_state and st.session_state.get("eleicao_id") == eleicao_id:
            st.subheader("Registrar voto")
            candidatos_eleicao = candidatos[candidatos['eleicao_id']==eleicao_id]['nome'].tolist()

            if candidatos_eleicao:
                candidato = st.radio("Escolha seu candidato:", candidatos_eleicao)
                if st.button("Confirmar Voto"):
                    token_h = sha256(st.session_state["token"])
                    vote_hash = sha256(token_h + candidato + secrets.token_hex(8))

                    try:
                        # Registrar voto anonimamente
                        cur.execute(
                            "INSERT INTO eleitores (datahora, eleicao_id, candidato, token_hash, vote_hash) VALUES (%s,%s,%s,%s,%s)",
                            (datetime.utcnow(), eleicao_id, candidato, token_h, vote_hash)
                        )
                        # Atualizar vote_hash na tabela votos
                        cur.execute(
                            "UPDATE votos SET vote_hash=%s WHERE token_hash=%s AND eleicao_id=%s",
                            (vote_hash, token_h, eleicao_id)
                        )
                        conn.commit()

                        st.success(f"✅ Voto registrado com sucesso para **{candidato}**!")
                        st.info("⚠️ O token foi descartado após o voto.")
                        del st.session_state["token"]
                        del st.session_state["eleicao_id"]

                        # Forçar recarregamento sem experimental_rerun
                        st.experimental_set_query_params(refresh=str(datetime.utcnow()))
                    except Exception as e:
                        st.error(f"Erro ao registrar voto: {e}")
            else:
                st.warning("Nenhum candidato cadastrado para esta eleição.")
    else:
        st.success("✅ Você já votou em todas as eleições ativas!")
else:
    st.info("Preencha seu nome e número do CREA para continuar.")

# --- Resultados ---
st.title("🏆 Resultados das Eleições Senge-PR")
for idx, row in active_elections.iterrows():
    eleicao_id = row['id']
    votos_eleicao = votos[votos['eleicao_id']==eleicao_id]

    st.subheader(f"{row['nome']}")
    total_votos = len(votos_eleicao)
    st.write(f"Total de votos registrados: {total_votos}")

    if total_votos >= MIN_VOTOS:
        first_vote_time = votos_eleicao['datahora'].min()
        prazo_liberacao = first_vote_time + timedelta(minutes=TEMPO_LIMITE_MIN)
        agora = datetime.utcnow()

        if agora >= prazo_liberacao:
            st.success("Resultados liberados:")
            contagem = votos_eleicao.merge(eleitores[['token_hash','candidato']], on='token_hash')
            contagem = contagem['candidato'].value_counts().reset_index()
            contagem.columns = ['Candidato', 'Votos']
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
    st.dataframe(votos)
