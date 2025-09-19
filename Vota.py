import streamlit as st
import hashlib, secrets
import psycopg2
from datetime import datetime, timedelta
import os
import pandas as pd
from dotenv import load_dotenv

# --- Carregar variáveis do .env ---
load_dotenv()
HOST = os.getenv("SUPABASE_HOST")  # ex: aws-1-sa-east-1.pooler.supabase.com
DBNAME = os.getenv("SUPABASE_DB")  # postgres
USER = os.getenv("SUPABASE_USER")  # ex: postgres.ngzynmnsjiyfzeulchxy
PASSWORD = os.getenv("SUPABASE_PASSWORD")
PORT = int(os.getenv("SUPABASE_PORT"))  # 6543

# --- Configurações ---
MIN_VOTOS = 2
TEMPO_LIMITE_MIN = 30  # minutos

# --- Conectar ao Supabase/Postgres ---
try:
    conn = psycopg2.connect(
        host=HOST,
        dbname=DBNAME,
        user=USER,
        password=PASSWORD,
        port=PORT,
        sslmode="require"
    )
    cur = conn.cursor()
except Exception as e:
    st.error(f"Erro ao conectar ao banco: {e}")
    st.stop()

# --- Carregar dados ---
def carregar_eleicoes():
    cur.execute("SELECT id, titulo, ativa FROM eleicoes;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["id", "titulo", "ativa"])

def carregar_candidatos():
    cur.execute("SELECT id, nome, eleicao_id FROM candidatos;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["id","nome","eleicao_id"])

def carregar_votos_registro():
    cur.execute("SELECT id, eleitor_id, eleicao_id, datahora FROM votos_registro;")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["id","eleitor_id","eleicao_id","datahora"])
    df['datahora'] = pd.to_datetime(df['datahora'], errors='coerce')
    return df

eleicoes = carregar_eleicoes()
candidatos = carregar_candidatos()
votos_registro = carregar_votos_registro()

# --- Streamlit UI ---
st.title("🗳 Sistema de Votação Senge-PR")

# --- Login ---
if "logged_in" not in st.session_state:
    st.subheader("Login do Eleitor")
    nome_input = st.text_input("Nome completo")
    crea_input = st.text_input("Número do CREA")
    if st.button("Entrar"):
        if nome_input.strip() == "" or crea_input.strip() == "":
            st.error("Preencha ambos os campos para continuar.")
        else:
            # Aqui usamos CREA como identificador do eleitor
            st.session_state["nome"] = nome_input.strip()
            st.session_state["crea"] = crea_input.strip()
            st.session_state["logged_in"] = True

# --- Votação ---
if st.session_state.get("logged_in"):
    nome = st.session_state["nome"]
    crea = st.session_state["crea"]
    st.info(f"Eleitor: **{nome}** | CREA: **{crea}**")

    active_eleicoes = eleicoes[eleicoes['ativa'] == True]
    st.subheader("Registrar votos em todas as eleições ativas")

    votos_a_inserir = []
    for _, eleicao in active_eleicoes.iterrows():
        eleicao_id = eleicao['id']
        candidatos_eleicao = candidatos[candidatos['eleicao_id']==eleicao_id]['nome'].tolist()
        if not candidatos_eleicao:
            st.warning(f"Nenhum candidato cadastrado para {eleicao['titulo']}")
            continue

        # Verifica se já votou
        ja_votou = ((votos_registro['eleicao_id'] == eleicao_id) &
                    (votos_registro['eleitor_id'] == crea)).any()
        if ja_votou:
            st.success(f"✅ Já votou na eleição {eleicao['titulo']}")
        else:
            voto = st.radio(f"Escolha seu candidato para {eleicao['titulo']}:", candidatos_eleicao, key=eleicao_id)
            votos_a_inserir.append((eleicao_id, voto))

    if votos_a_inserir and st.button("Confirmar todos os votos"):
        for eleicao_id, candidato_nome in votos_a_inserir:
            # Pegar id do candidato
            candidato_id = candidatos[(candidatos['eleicao_id']==eleicao_id) & (candidatos['nome']==candidato_nome)]['id'].iloc[0]
            try:
                # Inserir voto secreto
                cur.execute(
                    "INSERT INTO votos (eleicao_id, candidato_id) VALUES (%s, %s)",
                    (eleicao_id, candidato_id)
                )
                # Registrar que eleitor votou
                cur.execute(
                    "INSERT INTO votos_registro (eleitor_id, eleicao_id) VALUES (%s, %s)",
                    (crea, eleicao_id)
                )
                conn.commit()
                st.success(f"✅ Voto registrado para {candidato_nome} na eleição {eleicoes.loc[eleicoes['id']==eleicao_id,'titulo'].iloc[0]}!")
            except psycopg2.IntegrityError:
                conn.rollback()
                st.error(f"Você já votou na eleição {eleicoes.loc[eleicoes['id']==eleicao_id,'titulo'].iloc[0]}")
            except Exception as e:
                conn.rollback()
                st.error(f"Erro ao registrar voto na eleição {eleicoes.loc[eleicoes['id']==eleicao_id,'titulo'].iloc[0]}: {e}")

# --- Resultados ---
st.title("🏆 Resultados das Eleições Senge-PR")
for _, eleicao in active_eleicoes.iterrows():
    eleicao_id = eleicao['id']
    cur.execute("SELECT v.id, c.nome FROM votos v JOIN candidatos c ON v.candidato_id = c.id WHERE v.eleicao_id = %s", (eleicao_id,))
    votos_eleicao = cur.fetchall()
    total_votos = len(votos_eleicao)
    st.subheader(f"{eleicao['titulo']}")
    st.write(f"Total de votos registrados: {total_votos}")

    if total_votos >= MIN_VOTOS:
        df_votos = pd.DataFrame(votos_eleicao, columns=["id","candidato"])
        contagem = df_votos.groupby('candidato').size().reset_index(name='Votos')
        st.table(contagem)
    else:
        st.warning(f"Aguardando pelo menos {MIN_VOTOS} votos para exibir resultados.")
