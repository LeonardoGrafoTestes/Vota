import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta

# ------------------ CONFIGURAÇÕES ------------------
MOSTRAR_BRANCO_NULO = 1   # 0 = esconder BRANCO/NULO | 1 = mostrar
MIN_VOTOS = 2             # mínimo de votos para mostrar o resultado
TEMPO_ESPERA_MIN = 0      # minutos após o início para liberar resultado

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

def registrar_branco(eleitor_id, eleicoes):
    conn = get_connection()
    if conn:
        cur = conn.cursor()

        cur.execute("SELECT eleicao_id FROM votos_registro WHERE eleitor_id = %s AND eleicao_id = ANY(%s)",
                    (eleitor_id, [e[0] for e in eleicoes]))
        ja_votadas = [row[0] for row in cur.fetchall()]
        if ja_votadas:
            cur.close()
            return False, f"Você já votou nas eleições: {ja_votadas}"

        for eleicao_id, _, _ in eleicoes:
            cur.execute("SELECT id FROM candidatos WHERE eleicao_id = %s AND UPPER(nome)='BRANCO'", (eleicao_id,))
            candidato = cur.fetchone()
            if candidato:
                candidato_id = candidato[0]
                cur.execute("INSERT INTO votos (eleicao_id, candidato_id, datahora) VALUES (%s,%s,%s)",
                            (eleicao_id, candidato_id, datetime.now()))
                cur.execute("INSERT INTO votos_registro (eleitor_id, eleicao_id, datahora) VALUES (%s,%s,%s)",
                            (eleitor_id, eleicao_id, datetime.now()))

        conn.commit()
        cur.close()
        return True, "🤍 Voto BRANCO registrado!"
    return False, "Erro de conexão."

def registrar_nulo(eleitor_id, eleicoes):
    conn = get_connection()
    if conn:
        cur = conn.cursor()

        cur.execute("SELECT eleicao_id FROM votos_registro WHERE eleitor_id = %s AND eleicao_id = ANY(%s)",
                    (eleitor_id, [e[0] for e in eleicoes]))
        ja_votadas = [row[0] for row in cur.fetchall()]
        if ja_votadas:
            cur.close()
            return False, f"Você já votou nas eleições: {ja_votadas}"

        for eleicao_id, _, _ in eleicoes:
            cur.execute("SELECT id FROM candidatos WHERE eleicao_id = %s AND UPPER(nome)='NULO'", (eleicao_id,))
            candidato = cur.fetchone()
            if candidato:
                candidato_id = candidato[0]
                cur.execute("INSERT INTO votos (eleicao_id, candidato_id, datahora) VALUES (%s,%s,%s)",
                            (eleicao_id, candidato_id, datetime.now()))
                cur.execute("INSERT INTO votos_registro (eleitor_id, eleicao_id, datahora) VALUES (%s,%s,%s)",
                            (eleitor_id, eleicao_id, datetime.now()))

        conn.commit()
        cur.close()
        return True, "🚫 Voto NULO registrado!"
    return False, "Erro de conexão."

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
        return True, "✅ Votos confirmados!"
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
            WHERE e.ativa = true
            GROUP BY e.id, e.titulo, e.data_inicio, c.id, c.nome
        """)
        rows = cur.fetchall()
        cur.close()
        return rows
    return []

# ==========================================================
# POP-UPS DE CONFIRMAÇÃO
# ==========================================================
@st.dialog("Confirmar votos")
def popup_confirmar_votos(eleitor_id, escolhas):
    st.write("Confirma todos seus votos?")
    if st.button("✅ Confirmar"):
        sucesso, msg = registrar_votos(eleitor_id, escolhas)
        if sucesso:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

@st.dialog("Confirmar Branco")
def popup_confirmar_branco(eleitor_id, eleicoes):
    st.write("Confirma voto BRANCO?")
    if st.button("🤍 Confirmar Branco"):
        sucesso, msg = registrar_branco(eleitor_id, eleicoes)
        if sucesso:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

@st.dialog("Confirmar Nulo")
def popup_confirmar_nulo(eleitor_id, eleicoes):
    st.write("Confirma voto NULO?")
    if st.button("🚫 Confirmar Nulo"):
        sucesso, msg = registrar_nulo(eleitor_id, eleicoes)
        if sucesso:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

# ------------------ INTERFACE ------------------
st.title("🗳️ Sistema de Votação Online")
menu = st.sidebar.radio("Navegação", ["Login", "Votar", "Resultados"])

# LOGIN
if menu == "Login":
    st.subheader("🔑 Login do Eleitor")
    nome = st.text_input("Nome completo")
    crea = st.text_input("Número do Conselho")
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

# VOTAÇÃO
elif menu == "Votar":
    if "eleitor_id" not in st.session_state:
        st.warning("⚠️ Faça login primeiro!")
    else:
        st.subheader("🗳️ Votação")
        eleicoes = get_eleicoes()
        if not eleicoes:
            st.info("Nenhuma eleição ativa.")
        else:
            escolhas = {}
            for eleicao_id, titulo, _ in eleicoes:
                st.write(f"### {titulo}")
                cur_cands = get_connection().cursor()
                cur_cands.execute("SELECT id, nome FROM candidatos WHERE eleicao_id=%s AND UPPER(nome) NOT IN ('BRANCO','NULO')", (eleicao_id,))
                cand_rows = cur_cands.fetchall()
                cur_cands.close()

                nomes = {c[1]: c[0] for c in cand_rows}
                if not nomes:
                    st.info("Nenhum candidato disponível.")
                    continue

                escolhido = st.radio("Escolha:", list(nomes.keys()), key=f"e_{eleicao_id}")
                escolhas[eleicao_id] = nomes[escolhido]

            col1, col2, col3 = st.columns(3)

            with col1:
                if escolhas and len(escolhas) == len(eleicoes):
                    if st.button("✅ Confirmar votos"):
                        popup_confirmar_votos(st.session_state["eleitor_id"], escolhas)
                else:
                    st.info("Vote em todas antes de confirmar.")

            with col2:
                if st.button("🤍 Branco"):
                    popup_confirmar_branco(st.session_state["eleitor_id"], eleicoes)

            with col3:
                if st.button("🚫 Nulo"):
                    popup_confirmar_nulo(st.session_state["eleitor_id"], eleicoes)

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
                st.warning(f"⚠️ Aguardando {MIN_VOTOS}+ votos para {sub['Eleição'].iloc[0]}")
                continue

            if agora < data_inicio + timedelta(minutes=TEMPO_ESPERA_MIN):
                st.warning("⏳ Resultado ainda bloqueado por tempo.")
                continue

            # 🧠 classificar e ordenar
            def classifica(nome):
                n = nome.upper()
                if n == "BRANCO": return 2
                if n == "NULO": return 3
                return 1

            sub["ordem"] = sub["Candidato"].map(classifica)

            sub = sub.sort_values(by=["ordem", "Votos"], ascending=[True, False])
            sub["%"] = sub["Votos"] / total_votos * 100

            st.write(f"### {sub['Eleição'].iloc[0]}")

            tabela = sub[["Candidato", "Votos", "%"]].style \
                .format({"%": "{:.1f}%"}) \
                .hide(axis="index")

            st.dataframe(tabela, use_container_width=True, hide_index=True)

# ------------------ RODAPÉ ------------------
st.markdown(
    f"""
    <style>
    .rodape {{
        position: fixed;
        left: 50%;
        bottom: 10px;
        transform: translateX(-50%);
        color: #999;
        font-size: 14px;
        font-family: "Segoe UI", sans-serif;
        text-align: center;
    }}
    </style>
    <div class="rodape">👨‍💻 Desenvolvido por <b>Leonardo Dutra</b> © {datetime.now().year}</div>
    """,
    unsafe_allow_html=True
)
