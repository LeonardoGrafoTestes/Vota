import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import re

# ------------------ CONFIGURAÇÕES ------------------
MOSTRAR_BRANCO_NULO = 0   # 0 = esconder BRANCO/NULO | 1 = mostrar
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
def ja_votou_todas(eleitor_id):
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(DISTINCT id) FROM eleicoes WHERE ativa = true")
        total_eleicoes = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT eleicao_id) FROM votos_registro WHERE eleitor_id = %s", (eleitor_id,))
        total_votadas = cur.fetchone()[0]
        cur.close()

        return total_votadas >= total_eleicoes
    return False

def get_eleicoes():
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT id, titulo, data_inicio FROM eleicoes WHERE ativa = true ORDER BY id")
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
        if cur.fetchall():
            cur.close()
            return False, "Você já votou nessa eleição."

        for eleicao_id, candidato_id in escolhas.items():
            cur.execute("INSERT INTO votos (eleicao_id, candidato_id, datahora) VALUES (%s,%s,%s)",
                        (eleicao_id, candidato_id, datetime.now()))
            cur.execute("INSERT INTO votos_registro (eleitor_id, eleicao_id, datahora) VALUES (%s,%s,%s)",
                        (eleitor_id, eleicao_id, datetime.now()))

        conn.commit()
        cur.close()
        return True, "✅ Voto registrado com sucesso!"
    return False, "Erro de conexão."

def registrar_branco(eleitor_id, eleicoes):
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        for eleicao_id, _, _ in eleicoes:
            cur.execute("SELECT id FROM candidatos WHERE eleicao_id = %s AND UPPER(nome)='BRANCO'", (eleicao_id,))
            bn = cur.fetchone()
            if bn:
                cur.execute("INSERT INTO votos (eleicao_id, candidato_id, datahora) VALUES (%s,%s,%s)",
                            (eleicao_id, bn[0], datetime.now()))
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
        for eleicao_id, _, _ in eleicoes:
            cur.execute("SELECT id FROM candidatos WHERE eleicao_id = %s AND UPPER(nome)='NULO'", (eleicao_id,))
            nu = cur.fetchone()
            if nu:
                cur.execute("INSERT INTO votos (eleicao_id, candidato_id, datahora) VALUES (%s,%s,%s)",
                            (eleicao_id, nu[0], datetime.now()))
                cur.execute("INSERT INTO votos_registro (eleitor_id, eleicao_id, datahora) VALUES (%s,%s,%s)",
                            (eleitor_id, eleicao_id, datetime.now()))

        conn.commit()
        cur.close()
        return True, "🚫 Voto NULO registrado!"
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
            ORDER BY e.id, votos DESC
        """)
        rows = cur.fetchall()
        cur.close()
        return rows
    return []

# Pop-ups
@st.dialog("Confirmar Votos")
def popup_confirmar_votos(eleitor_id, escolhas):
    if st.button("✅ Confirmar"):
        ok, msg = registrar_votos(eleitor_id, escolhas)
        if ok:
            st.session_state["mensagem_pos_voto"] = "✅ Você já votou em todas as eleições!"
            st.rerun()
        else:
            st.error(msg)

@st.dialog("Confirmar voto Branco")
def popup_confirmar_branco(eleitor_id, eleicoes):
    if st.button("🤍 Confirmar Branco"):
        ok, msg = registrar_branco(eleitor_id, eleicoes)
        if ok:
            st.session_state["mensagem_pos_voto"] = "✅ Você já votou em todas as eleições!"
            st.rerun()
        else:
            st.error(msg)

@st.dialog("Confirmar voto Nulo")
def popup_confirmar_nulo(eleitor_id, eleicoes):
    if st.button("🚫 Confirmar Nulo"):
        ok, msg = registrar_nulo(eleitor_id, eleicoes)
        if ok:
            st.session_state["mensagem_pos_voto"] = "✅ Você já votou em todas as eleições!"
            st.rerun()
        else:
            st.error(msg)

# ------------------ UI ------------------
st.title("🗳️ Sistema de Votação Online")
menu = st.sidebar.radio("Menu", ["Login", "Votar", "Resultados"])

# ==========================================================
# LOGIN
# ==========================================================
if menu == "Login":
    st.subheader("🔑 Login do Eleitor")

    nome = st.text_input("Nome completo")
    conselho = st.text_input("Número do Conselho (Apenas número)")  # ← novo nome do campo
    email = st.text_input("Email (opcional)")

    if st.button("Entrar"):

        # ---- VALIDAÇÃO NOME ----
        if not nome:
            st.error("O campo Nome é obrigatório.")
            st.stop()

        if re.search(r"\d", nome):
            st.error("O nome não pode conter números.")
            st.stop()

        if len(nome.strip().split()) < 2:
            st.error("Informe nome e sobrenome.")
            st.stop()

        # ---- VALIDAÇÃO NÚMERO DO CONSELHO ----
        if not conselho:
            st.error("O campo Número do Conselho é obrigatório.")
            st.stop()

        if not conselho.isdigit():
            st.error("O Número do Conselho deve conter apenas números.")
            st.stop()

        # ---- LOGIN OU CADASTRO ----
        conn = get_connection()
        cur = conn.cursor()

        # validar voto anterior pelo número do conselho
        cur.execute("SELECT id, nome FROM eleitores WHERE crea = %s", (conselho,))
        eleitor = cur.fetchone()

        if eleitor:
            st.session_state["eleitor_id"] = eleitor[0]
            st.session_state["nome"] = eleitor[1]
        else:
            cur.execute(
                "INSERT INTO eleitores (nome, crea, email, data_cadastro) VALUES (%s,%s,%s,%s) RETURNING id",
                (nome, conselho, email if email else None, datetime.now())
            )
            novo_id = cur.fetchone()[0]
            conn.commit()
            st.session_state["eleitor_id"] = novo_id
            st.session_state["nome"] = nome

        cur.close()
        st.success(f"Bem-vindo(a), {st.session_state['nome']}!")

# ==========================================================
# VOTAR
# ==========================================================
elif menu == "Votar":
    if "eleitor_id" not in st.session_state:
        st.warning("⚠️ Faça login primeiro!")
    else:
        eleitor_id = st.session_state["eleitor_id"]

        # Mensagem pós-voto (se existir)
        if "mensagem_pos_voto" in st.session_state:
            st.success(st.session_state["mensagem_pos_voto"])

        if ja_votou_todas(eleitor_id):
            st.success("✅ Você já votou em todas as eleições!")
            st.info("Obrigado pela sua participação!")
            st.stop()

        eleicoes = get_eleicoes()
        escolhas = {}
        conn = get_connection()

        for eleicao_id, titulo, data_inicio in eleicoes:
            st.write(f"### {titulo}")

            cur = conn.cursor()
            cur.execute("SELECT id, nome FROM candidatos WHERE eleicao_id=%s", (eleicao_id,))
            cand_rows = cur.fetchall()
            cur.close()

            if MOSTRAR_BRANCO_NULO == 0:
                cand_rows = [c for c in cand_rows if c[1].upper().strip() not in ("BRANCO","NULO")]

            def ordem(nome):
                n = nome.upper().strip()
                if n == "BRANCO": return 2
                if n == "NULO": return 3
                return 1

            cand_rows = sorted(cand_rows, key=lambda x: ordem(x[1]))
            nomes = {c[1]: c[0] for c in cand_rows}

            if nomes:
                voto = st.radio("Escolha:", list(nomes.keys()), key=f"radio_{eleicao_id}")
                escolhas[eleicao_id] = nomes[voto]

        col1, col2, col3 = st.columns(3)

        with col1:
            if len(escolhas) == len(eleicoes):
                if st.button("✅ Confirmar"):
                    popup_confirmar_votos(eleitor_id, escolhas)

        with col2:
            if MOSTRAR_BRANCO_NULO == 0:
                if st.button("🤍 Branco"):
                    popup_confirmar_branco(eleitor_id, eleicoes)

        with col3:
            if MOSTRAR_BRANCO_NULO == 0:
                if st.button("🚫 Nulo"):
                    popup_confirmar_nulo(eleitor_id, eleicoes)

# ==========================================================
# RESULTADOS
# ==========================================================
elif menu == "Resultados":
    st.subheader("📊 Resultados")

    resultados = get_resultados()
    if not resultados:
        st.info("Nenhum resultado disponível.")
    else:
        df = pd.DataFrame(resultados, columns=["eleicao_id","Eleição","Data Início","Candidato","Votos"])

        for eleicao_id in df["eleicao_id"].unique():
            sub = df[df["eleicao_id"] == eleicao_id].copy()
            total = sub["Votos"].sum()
            data_inicio = sub["Data Início"].iloc[0]

            if total < MIN_VOTOS:
                st.warning(f"⚠️ Resultados apenas com {MIN_VOTOS}+ votos.")
                continue

            if datetime.now() < data_inicio + timedelta(minutes=TEMPO_ESPERA_MIN):
                st.warning("⏳ Aguardando tempo de liberação.")
                continue

            sub["ordem"] = sub["Candidato"].map(lambda n: 2 if n.upper()=="BRANCO" else 3 if n.upper()=="NULO" else 1)
            sub = sub.sort_values(by=["ordem","Votos"], ascending=[True, False])
            sub["%"] = sub["Votos"] / total * 100

            st.write(f"### {sub['Eleição'].iloc[0]}")
            tabela = sub[["Candidato","Votos","%"]].style.format({"%":"{:.1f}%"}).hide(axis="index")
            st.dataframe(tabela, use_container_width=True, hide_index=True)

# ==========================================================
# RODAPÉ
# ==========================================================
st.markdown(
    f"""
    <div style='position:fixed;bottom:10px;left:50%;transform:translate(-50%);color:#999;font-size:14px'>
    👨‍💻 Desenvolvido por <b>Leonardo Dutra</b> © {datetime.now().year}
    </div>
    """, unsafe_allow_html=True)

