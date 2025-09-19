import streamlit as st
import psycopg2
from datetime import datetime, timedelta
import pandas as pd

# --- Conexão com o banco via Streamlit Secrets ---
HOST = st.secrets["SUPABASE_HOST"]
DBNAME = st.secrets["SUPABASE_DB"]
USER = st.secrets["SUPABASE_USER"]
PASSWORD = st.secrets["SUPABASE_PASSWORD"]
PORT = st.secrets["SUPABASE_PORT"]

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
    st.error(f"Erro ao conectar ao banco: {e}")
    st.stop()

# --- Configurações ---
MIN_VOTOS = 2
TEMPO_LIMITE_MIN = 30  # minutos

# --- Funções para carregar dados ---
def carregar_eleicoes():
    cur.execute("SELECT id, titulo, ativa FROM eleicoes;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["id","titulo","ativa"])

def carregar_candidatos():
    cur.execute("SELECT id, nome, eleicao_id FROM candidatos;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["id","nome","eleicao_id"])

def carregar_votos():
    cur.execute("SELECT id, eleicao_id, candidato_id, datahora FROM votos;")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["id","eleicao_id","candidato_id","datahora"])
    df['datahora'] = pd.to_datetime(df['datahora'], errors='coerce')
    return df

def carregar_votos_registro():
    cur.execute("SELECT id, eleitor_id, eleicao_id, datahora FROM votos_registro;")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["id","eleitor_id","eleicao_id","datahora"])
    df['datahora'] = pd.to_datetime(df['datahora'], errors='coerce')
    return df

def carregar_eleitores():
    cur.execute("SELECT id, nome, crea FROM eleitores;")
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["id","nome","crea"])

# --- Carregar dados iniciais ---
eleicoes = carregar_eleicoes()
candidatos = carregar_candidatos()
votos = carregar_votos()
votos_registro = carregar_votos_registro()
eleitores = carregar_eleitores()

active_elections = eleicoes[eleicoes['ativa'] == True]

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
            # Verifica se eleitor já existe, se não cria
            eleitor = eleitores[(eleitores['nome']==nome_input.strip()) & (eleitores['crea']==crea_input.strip())]
            if eleitor.empty:
                cur.execute(
                    "INSERT INTO eleitores (nome, crea) VALUES (%s,%s) RETURNING id",
                    (nome_input.strip(), crea_input.strip())
                )
                conn.commit()
                eleitor_id = cur.fetchone()[0]
            else:
                eleitor_id = int(eleitor['id'].values[0])
            st.session_state["eleitor_id"] = eleitor_id
            st.session_state["logged_in"] = True
            st.session_state["nome"] = nome_input.strip()
            st.session_state["crea"] = crea_input.strip()

# --- Fluxo de votação ---
if st.session_state.get("logged_in"):
    st.info(f"Eleitor: **{st.session_state['nome']}** | CREA: **{st.session_state['crea']}**")
    eleitor_id = st.session_state["eleitor_id"]

    votos_registro = carregar_votos_registro()
    votos = carregar_votos()

    st.subheader("Registrar votos em todas as eleições ativas")
    voto_confirmado = False

    votos_para_registrar = {}

    for idx, eleicao in active_elections.iterrows():
        eleicao_id = eleicao['id']
        st.write(f"**{eleicao['titulo']}**")

        # Verifica se eleitor já votou nessa eleição
        if ((votos_registro['eleitor_id']==eleitor_id) & (votos_registro['eleicao_id']==eleicao_id)).any():
            st.success("✅ Já votou nesta eleição")
            continue

        candidatos_eleicao = candidatos[candidatos['eleicao_id']==eleicao_id]
        candidato_nome = st.radio(f"Escolha seu candidato para {eleicao['titulo']}:", candidatos_eleicao['nome'].tolist(), key=f"eleicao_{eleicao_id}")
        votos_para_registrar[eleicao_id] = candidatos_eleicao[candidatos_eleicao['nome']==candidato_nome]['id'].values[0]

    if votos_para_registrar and st.button("Confirmar Votos"):
        for eleicao_id, candidato_id in votos_para_registrar.items():
            try:
                # Voto secreto
                cur.execute(
                    "INSERT INTO votos (eleicao_id, candidato_id) VALUES (%s,%s)",
                    (eleicao_id, candidato_id)
                )
                # Registro de quem votou
                cur.execute(
                    "INSERT INTO votos_registro (eleitor_id, eleicao_id) VALUES (%s,%s)",
                    (eleitor_id, eleicao_id)
                )
                conn.commit()
                voto_confirmado = True
            except Exception as e:
                conn.rollback()
                st.error(f"Erro ao registrar voto na eleição {eleicao_id}: {e}")

        if voto_confirmado:
            st.success("✅ Votos registrados com sucesso!")

# --- Resultados ---
st.title("🏆 Resultados das Eleições Senge-PR")
for idx, eleicao in active_elections.iterrows():
    eleicao_id = eleicao['id']
    votos_eleicao = votos[votos['eleicao_id']==eleicao_id]
    total_votos = len(votos_eleicao)

    st.subheader(f"{eleicao['titulo']}")
    st.write(f"Total de votos registrados: {total_votos}")

    if total_votos >= MIN_VOTOS:
        first_vote_time = votos_eleicao['datahora'].min()
        prazo_liberacao = first_vote_time + timedelta(minutes=TEMPO_LIMITE_MIN)
        agora = datetime.utcnow()
        if agora >= prazo_liberacao:
            contagem = votos_eleicao.groupby('candidato_id').size().reset_index(name='Votos')
            # Juntando com nomes dos candidatos
            contagem = contagem.merge(candidatos[['id','nome']], left_on='candidato_id', right_on='id', how='left')
            contagem = contagem[['nome','Votos']]
            st.table(contagem)
        else:
            st.info(f"Resultados serão liberados após {TEMPO_LIMITE_MIN} minutos desde o primeiro voto.\nPrazo: {prazo_liberacao}")
    else:
        st.warning(f"Aguardando pelo menos {MIN_VOTOS} votos para exibir resultados.")
