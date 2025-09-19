import streamlit as st
import psycopg2

st.title("Teste de Conexão com Supabase")

def get_connection():
    """Tenta conectar ao banco e mantém a conexão ativa na sessão"""
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
            st.success("✅ Conexão com o banco de dados OK!")
        except Exception as e:
            st.error(f"❌ Erro ao conectar ao banco: {e}")
            return None
    return st.session_state["conn"]

# Botão para testar
if st.button("Testar Conexão"):
    conn = get_connection()
    if conn:
        st.write("Conexão estabelecida com sucesso!")
        try:
            cur = conn.cursor()
            cur.execute("SELECT now();")
            result = cur.fetchone()
            st.write("Hora atual do banco:", result[0])
            cur.close()
        except Exception as e:
            st.error(f"Erro ao executar query: {e}")
