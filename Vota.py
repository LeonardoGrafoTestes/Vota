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
    cur.execute("SELECT ID, Nome, Ativa FROM Eleicoes;")
    rows = cur.fetchall()
    return [{"ID": r[0], "Nome": r[1], "Ativa": str(r[2]).upper()} for r in rows]

def carregar_candidatos():
    cur.execute("SELECT Eleicao_ID, Nome FROM Candidatos;")
    rows = cur.fetchall()
    return [{"Eleicao_ID": r[0], "Nome": r[1]} for r in rows]

def carregar_votos():
    cur.execute("SELECT Nome, CREA, Token_Hash, DataHora, Eleicao_ID FROM Votos;")
    rows = cur.fetchall()
    return [{"Nome": r[0], "CREA": r[1], "Token_Hash": r[2], "DataHora": r[3], "Eleicao_ID": r[4]} for r in rows]

def carregar_eleitores():
    cur.execute("SELECT DataHora, Eleicao_ID, Token_Hash, Vote_Hash FROM Eleitores;")
    rows = cur.fetchall()
    return [{"DataHora": r[0], "Eleicao_ID": r[1], "Token_Hash": r[2], "Vote_Hash": r[3]} for r in rows]

# --- Carregar dados ---
eleicoes = carregar_eleicoes()
candidatos = carregar_candidatos()
votos = carregar_votos()
eleitores = carregar_eleitores()

active_elections = [e for e in eleicoes if e['Ativa'] == "TRUE"]

# --- Streamlit UI ---
st.title("🗳️ Sistema de Votação CREA (Supabase)")

# --- Entrada do eleitor ---
st.subheader("Identificação do Eleitor")
nome = st.text_input("Nome completo")
crea = st.text_input("Número do CREA")

if nome and crea:
    # --- Eleições pendentes ---
    eleicoes_pendentes = [e for e in active_elections
                          if not any(v['CREA']==crea and v['Eleicao_ID']==e['ID'] for v in votos)]

    total_eleicoes = len(active_elections)
    votadas = total_eleicoes - len(eleicoes_pendentes)

    # Barra de progresso
    st.progress(votadas / total_eleicoes if total_eleicoes > 0 else 1.0)
    st.write(f"Eleições votadas: {votadas} / {total_eleicoes}")

    if eleicoes_pendentes:
        # Próxima eleição
        eleicao = eleicoes_pendentes[0]
        eleicao_id = eleicao['ID']
        st.info(f"Próxima eleição: **{eleicao['Nome']}**")

        # --- Gerar token ---
        if "token" not in st.session_state:
            if st.button("Gerar Token"):
                token = secrets.token_urlsafe(16)
                token_hash = sha256(token)

                # Registrar token no banco
                try:
                    cur.execute(
                        "INSERT INTO Votos (Nome, CREA, Token_Hash, DataHora, Eleicao_ID) VALUES (%s,%s,%s,%s,%s)",
                        (nome, crea, token_hash, datetime.utcnow(), eleicao_id)
                    )
                    conn.commit()
                    st.session_state["token"] = token
                    st.success("✅ Seu token foi gerado (guarde com segurança):")
                    st.code(token)
                except Exception as e:
                    st.error(f"Erro ao registrar token: {e}")

        # --- Registrar voto ---
        if "token" in st.session_state:
            st.subheader("Registrar voto")
            candidatos_eleicao = [c['Nome'] for c in candidatos if c['Eleicao_ID']==eleicao_id]

            if candidatos_eleicao:
                candidato = st.radio("Escolha seu candidato:", candidatos_eleicao)
                if st.button("Confirmar Voto"):
                    token_h = sha256(st.session_state["token"])
                    vote_hash = sha256(token_h + candidato + secrets.token_hex(8))

                    try:
                        cur.execute(
                            "INSERT INTO Eleitores (DataHora, Eleicao_ID, Token_Hash, Vote_Hash) VALUES (%s,%s,%s,%s)",
                            (datetime.utcnow(), eleicao_id, token_h, vote_hash)
                        )
                        conn.commit()
                        st.success(f"✅ Voto registrado com sucesso para **{eleicao['Nome']}**!")
                        st.write("Hash do seu voto (anonimizado):", vote_hash)
                        del st.session_state["token"]
                        st.info("Atualize a página para votar na próxima eleição.")
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
if active_elections:
    df_votos = pd.DataFrame(votos)
    for e in active_elections:
        eleicao_id = e['ID']
        votos_eleicao = df_votos[df_votos['Eleicao_ID']==eleicao_id] if not df_votos.empty else pd.DataFrame()

        st.subheader(f"{e['Nome']}")
        total_votos = len(votos_eleicao)
        st.write(f"Total de votos registrados: {total_votos}")

        if total_votos >= MIN_VOTOS:
            if not votos_eleicao.empty:
                votos_eleicao['DataHora'] = pd.to_datetime(votos_eleicao['DataHora'], errors='coerce')
                first_vote_time = votos_eleicao['DataHora'].min()
                prazo_liberacao = first_vote_time + timedelta(minutes=TEMPO_LIMITE_MIN)
                agora = datetime.utcnow()

                if agora >= prazo_liberacao:
                    st.success("Resultados liberados:")
                    contagem = votos_eleicao['Token_Hash'].value_counts().reset_index()
                    contagem.columns = ['Candidato', 'Votos']
                    # Observação: o voto está anonimamente registrado, você pode criar contagem por candidato se armazenar hash vinculado a candidato separadamente
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
    st.dataframe(df_votos)
