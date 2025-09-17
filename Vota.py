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
    return pd.DataFrame(rows, columns=["ID","Nome","Ativa"])

def carregar_candidatos():
    cur.execute("SELECT Eleicao_ID, Nome FROM Candidatos;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["Eleicao_ID","Nome"])

def carregar_votos():
    cur.execute("SELECT Eleicao_ID, Token_Hash, candidato, Vote_Hash, DataHora FROM Eleitores;")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["Eleicao_ID","Token_Hash","candidato","Vote_Hash","DataHora"])
    df['DataHora'] = pd.to_datetime(df['DataHora'], errors='coerce')
    return df

def carregar_eleitores():
    cur.execute("SELECT Nome, CREA, Eleicao_ID, Token_Hash FROM Eleitores;")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["Nome","CREA","Eleicao_ID","Token_Hash"])
    return df

# --- Carregar dados ---
eleicoes = carregar_eleicoes()
candidatos = carregar_candidatos()
votos = carregar_votos()
eleitores = carregar_eleitores()

eleicoes['Ativa'] = eleicoes['Ativa'].astype(str).str.upper()
active_elections = eleicoes[eleicoes['Ativa'] == "TRUE"]

# --- Streamlit UI ---
st.title("🗳️ Sistema de Votação Anônima CREA")

# --- Entrada do eleitor ---
st.subheader("Identificação do Eleitor")
nome = st.text_input("Nome completo")
crea = st.text_input("Número do CREA")

if nome and crea:
    # --- Eleições pendentes ---
    eleicoes_pendentes = []
    for idx, row in active_elections.iterrows():
        eleicao_id = row['ID']
        # Verifica se já existe token ativo para o eleitor
        if not ((eleitores['CREA'] == crea) & (eleitores['Eleicao_ID'] == eleicao_id)).any():
            eleicoes_pendentes.append(row)

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

                # Registrar token no banco (sem gravar Nome/CREA no voto)
                try:
                    cur.execute(
                        "INSERT INTO Eleitores (Nome, CREA, Eleicao_ID, Token_Hash) VALUES (%s,%s,%s,%s)",
                        (nome, crea, eleicao_id, token_hash)
                    )
                    conn.commit()
                    st.session_state["token"] = token
                    st.success("✅ Seu token foi gerado (guarde com segurança):")
                    st.code(token)
                    # Recarrega eleitores
                    eleitores = carregar_eleitores()
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
                            "INSERT INTO Eleitores (Eleicao_ID, Token_Hash, candidato, Vote_Hash, DataHora) VALUES (%s,%s,%s,%s,%s)",
                            (eleicao_id, token_h, candidato, vote_hash, datetime.utcnow())
                        )
                        conn.commit()
                        st.success(f"✅ Voto registrado com sucesso para **{candidato}**!")
                        st.info("O token foi descartado após o voto.")
                        # Limpar token
                        del st.session_state["token"]
                        # Atualiza DataFrame votos
                        votos = carregar_votos()
                    except Exception as e:
                        st.error(f"Erro ao registrar voto: {e}")
            else:
                st.warning("Nenhum candidato cadastrado para esta eleição.")
    else:
        st.success("✅ Você já votou em todas as eleições ativas!")
else:
    st.info("Preencha seu nome e número do CREA para continuar.")

# --- Resultados ---
st.title("🏆 Resultados das Eleições")
for idx, row in active_elections.iterrows():
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
            contagem = votos_eleicao.groupby('candidato').size().reset_index(name='Votos')
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
