import streamlit as st
import psycopg2
import pandas as pd

# Conexão com o Supabase usando a URL do secrets
def get_connection():
    try:
        db_url = st.secrets["connections"]["supabase"]["url"]
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        st.error(f"Erro ao conectar ao banco: {e}")
        return None

# Função para autenticar eleitor
def autenticar_eleitor(nome, crea):
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT id, nome FROM eleitores WHERE nome = %s AND crea = %s", (nome, crea))
        eleitor = cur.fetchone()
        cur.close()
        conn.close()
        return eleitor
    return None

# Verificar eleições ativas
def get_eleicoes():
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT id, titulo, descricao FROM eleicoes WHERE ativa = true")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    return []

# Buscar candidatos de uma eleição
def get_candidatos(eleicao_id):
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT id, nome FROM candidatos WHERE eleicao_id = %s", (eleicao_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    return []

# Registrar voto secreto
def registrar_voto(eleitor_id, eleicao_id, candidato_id):
    conn = get_connection()
    if conn:
        cur = conn.cursor()

        # Verifica se já votou nessa eleição
        cur.execute("SELECT 1 FROM votos_registro WHERE eleitor_id = %s AND eleicao_id = %s", (eleitor_id, eleicao_id))
        if cur.fetchone():
            cur.close()
            conn.close()
            return False, "Você já votou nessa eleição."

        # Insere voto secreto
        cur.execute("INSERT INTO votos (eleicao_id, candidato_id) VALUES (%s, %s)", (eleicao_id, candidato_id))

        # Marca que o eleitor já votou
        cur.execute("INSERT INTO votos_registro (eleitor_id, eleicao_id) VALUES (%s, %s)", (eleitor_id, eleicao_id))

        conn.commit()
        cur.close()
        conn.close()
        return True, "Voto registrado com sucesso!"

    return False, "Erro de conexão."

# Mostrar resultados
def get_resultados(eleicao_id):
    conn = get_connection()
    if conn:
        query = """
        SELECT c.nome, COUNT(v.id) as total_votos
        FROM candidatos c
        LEFT JOIN votos v ON c.id = v.candidato_id
        WHERE c.eleicao_id = %s
        GROUP BY c.nome
        ORDER BY total_votos DESC
        """
        cur = conn.cursor()
        cur.execute(query, (eleicao_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    return []

# ------------------ INTERFACE STREAMLIT ------------------

st.title("🗳️ Sistema de Votação Online")

menu = st.sidebar.radio("Navegação", ["Login", "Votar", "Resultados"])

if menu == "Login":
    st.subheader("🔑 Login do Eleitor")
    nome = st.text_input("Nome")
    crea = st.text_input("CREA")

    if st.button("Entrar"):
        eleitor = autenticar_eleitor(nome, crea)
        if eleitor:
            st.session_state["eleitor_id"] = eleitor[0]
            st.success(f"Bem-vindo, {eleitor[1]}!")
        else:
            st.error("Eleitor não encontrado.")

elif menu == "Votar":
    if "eleitor_id" not in st.session_state:
        st.warning("⚠️ Faça login primeiro!")
    else:
        st.subheader("🗳️ Votação")

        eleicoes = get_eleicoes()
        if not eleicoes:
            st.info("Nenhuma eleição ativa no momento.")
        else:
            eleicao_opcao = st.selectbox("Escolha a eleição:", [f"{e[0]} - {e[1]}" for e in eleicoes])
            eleicao_id = int(eleicao_opcao.split(" - ")[0])

            candidatos = get_candidatos(eleicao_id)
            candidato_opcao = st.radio("Escolha seu candidato:", [f"{c[0]} - {c[1]}" for c in candidatos])

            candidato_id = int(candidato_opcao.split(" - ")[0])

            if st.button("Confirmar Voto"):
                sucesso, msg = registrar_voto(st.session_state["eleitor_id"], eleicao_id, candidato_id)
                if sucesso:
                    st.success(msg)
                else:
                    st.error(msg)

elif menu == "Resultados":
    st.subheader("📊 Resultados das Eleições")

    eleicoes = get_eleicoes()
    if not eleicoes:
        st.info("Nenhuma eleição ativa.")
    else:
        eleicao_opcao = st.selectbox("Escolha a eleição:", [f"{e[0]} - {e[1]}" for e in eleicoes])
        eleicao_id = int(eleicao_opcao.split(" - ")[0])

        resultados = get_resultados(eleicao_id)
        if resultados:
            df = pd.DataFrame(resultados, columns=["Candidato", "Total de Votos"])
            st.table(df)
        else:
            st.info("Ainda não há votos para essa eleição.")
