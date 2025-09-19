import streamlit as st
import psycopg2

def get_connection():
    """Mantém a conexão ativa durante a sessão"""
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
