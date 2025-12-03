import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta

# ------------------ CONFIGURAÇÕES ------------------
MIN_VOTOS = 2         # mínimo de votos para mostrar o resultado
TEMPO_ESPERA_MIN = 0  # minutos após o início para liberar resultado

# ------------------ CONEXÃO ------------------
def get_connection():
    if "conn" not in st.session_state:
        try:
            supabase = st.secrets["connections"]["supabase"]
            st.session_state["conn"] = psycopg2.connect(
                host=supabase["host"],
                port=int(supabase["port"]),
                dbname=supabase["dbname"],
                user=supabase["user"],
                password=supabase["password"]
            )
        except Exception as e:
            st.error(f"Erro ao conectar ao banco: {e}")
            return None
    return st.session_state["conn"]

# ------------------ FUNÇÕES ------------------
def get_eleicoes():
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT id, titulo, data_inicio FROM eleicoes WHERE ativa = true ORDER BY id")
        rows = cur.fetchall()
        cur.close()
        return rows
    return []

def get_candidatos(eleicao_id):
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT id, nome FROM candidatos WHERE eleicao_id = %s", (eleicao_id,))
        rows = cur.fetchall()
        cur.close()
        return rows
    return []

def registrar_votos(eleitor_id, escolhas):
    conn = get_connection()
    if conn:
        cur = conn.cursor()

        cur.execute("SELECT eleicao_id FROM votos_registro WHERE eleitor_id = %s AND eleicao_id = ANY(%s)",
                    (eleitor_id, list(escolhas.keys())))
        ja_votadas = [row[0] for row in cur.fetchall()]
        if ja_votadas:
            cur.close()
            return False, f"Você já votou nas eleições: {ja_votadas}"

        for eleicao_id, candidato_id in escolhas.items():
            cur.execute("INSERT INTO votos (eleicao_id, candidato_id, datahora) VALUES (%s,%s,%s)",
                        (eleicao_id, candidato_id, datetime.now()))
            cur.execute("INSERT INTO votos_registro (eleitor_id, eleicao_id, datahora) VALUES (%s,%s,%s)",
                        (eleitor_id, eleicao_id, datetime.now()))

        conn.commit()
        cur.close()
        return True, "✅ Voto registrado com sucesso! Obrigado por participar."
    return False, "Erro de conexão."

def get_resultados():
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT e.id, e.titulo, e.data_inicio, c.nome, COUNT(v.id) as votos
            FROM eleicoes e
            JOIN candidatos c ON e.id = c.eleicao_id
            LEFT JOIN votos v ON c.id = v.candidato_id
            GROUP BY e.id, e.titulo, e.data_inicio, c.id, c.nome
            ORDER BY e.id, votos DESC
        """)
        rows = cur.fetchall()
        cur.close()
        return rows
    return []

# ------------------ INTERFACE ------------------
st.title("🗳️ Sistema de Votação Online")

menu = st.sidebar.radio("Navegação", ["Login", "Votar", "Resultados"])

# LOGIN
if menu == "Login":
    st.subheader("🔑 Login do Eleitor")
    nome = st.text_input("Nome completo")
    crea = st.text_input("Número do CREA (apenas números)")
    email = st.text_input("Email (opcional)")

    if st.button("Entrar"):
        if not nome or not crea:
            st.error("Nome e CREA são obrigatórios.")
        else:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT id, nome FROM eleitores WHERE crea = %s", (crea,))
            eleitor = cur.fetchone()
            if eleitor:
                st.session_state["eleitor_id"] = eleitor[0]
                st.session_state["nome"] = eleitor[1]
            else:
                cur.execute(
                    "INSERT INTO eleitores (nome, crea, email, data_cadastro) VALUES (%s,%s,%s,%s) RETURNING id",
                    (nome, crea, email, datetime.now())
                )
                eleitor_id = cur.fetchone()[0]
                conn.commit()
                st.session_state["eleitor_id"] = eleitor_id
                st.session_state["nome"] = nome
            cur.close()
            st.success(f"Bem-vindo(a), {st.session_state['nome']}!")

# VOTAR
elif menu == "Votar":
    if "eleitor_id" not in st.session_state:
        st.warning("⚠️ Faça login primeiro!")
    else:
        st.subheader("🗳️ Votação")
        eleicoes = get_eleicoes()
        if not eleicoes:
            st.info("Nenhuma eleição ativa.")
        else:
            # Verifica se eleitor já votou em todas
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM votos_registro WHERE eleitor_id = %s", (st.session_state["eleitor_id"],))
            qtd_votadas = cur.fetchone()[0]
            cur.close()

            if qtd_votadas == len(eleicoes):
                st.success("✅ Você já votou em todas as eleições. Obrigado pela sua participação!")
            else:
                escolhas = {}
                for eleicao_id, titulo, data_inicio in eleicoes:
                    st.write(f"### {titulo}")
                    candidatos = get_candidatos(eleicao_id)

                    if not candidatos:
                        st.info("Nenhum candidato cadastrado.")
                        continue

                    escolhido = st.radio(
                        f"Escolha seu candidato para {titulo}:",
                        [f"{c[0]} - {c[1]}" for c in candidatos],
                        key=f"eleicao_{eleicao_id}"
                    )

                    if escolhido:
                        escolhas[eleicao_id] = int(escolhido.split(" - ")[0])

                if len(escolhas) == len(eleicoes):
                    if st.button("✅ Confirmar todos os votos"):
                        sucesso, msg = registrar_votos(st.session_state["eleitor_id"], escolhas)
                        if sucesso:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                else:
                    st.info("Você precisa votar em todas as eleições antes de confirmar.")

# RESULTADOS
elif menu == "Resultados":
    st.subheader("📊 Resultados das Eleições")
    resultados = get_resultados()

    if not resultados:
        st.info("Nenhum resultado disponível.")
    else:
        df = pd.DataFrame(resultados, columns=["eleicao_id", "Eleição", "Data Início", "Candidato", "Votos"])

        agora = datetime.now()
        for eleicao_id in df["eleicao_id"].unique():
            sub = df[df["eleicao_id"] == eleicao_id].copy()
            data_inicio = sub["Data Início"].iloc[0]
            total_votos = sub["Votos"].sum()

            if total_votos < MIN_VOTOS:
                st.warning(f"⚠️ Aguardando pelo menos {MIN_VOTOS} votos para mostrar resultados da eleição **{sub['Eleição'].iloc[0]}**.")
                continue

            if agora < data_inicio + timedelta(minutes=TEMPO_ESPERA_MIN):
                st.warning(f"⏳ Resultados da eleição **{sub['Eleição'].iloc[0]}** disponíveis após {TEMPO_ESPERA_MIN} minutos do início.")
                continue

            # Calcula % de votos
            sub["%"] = sub["Votos"] / total_votos * 100
            sub = sub.sort_values(by="Votos", ascending=False)

            st.write(f"### {sub['Eleição'].iloc[0]}")
            st.table(sub[["Candidato", "Votos", "%"]].style.format({"%": "{:.1f}%"}))


# ------------------ RODAPÉ CENTRALIZADO ------------------
st.markdown(
    f"""
    <style>
    .rodape {{
        position: fixed;
        left: 50%;
        bottom: 10px;
        transform: translateX(-50%);
        color: #999999;
        font-size: 14px;
        font-family: "Segoe UI", sans-serif;
        text-align: center;
    }}
    </style>
    <div class="rodape">👨‍💻 Desenvolvido por <b>Leonardo Dutra</b> © {datetime.now().year}</div>
    """,
    unsafe_allow_html=True
)


