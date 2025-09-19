import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta

# ------------------ CONFIGURAÇÕES ------------------
MIN_VOTOS = 2        # quantidade mínima de votos para liberar resultados
TEMPO_MINUTOS = 10   # tempo mínimo em minutos para liberar resultados após início

# ------------------ CONEXÃO ------------------
def get_connection():
    """Mantém a conexão ativa durante a sessão"""
    if "conn" not in st.session_state:
        try:
            supabase = st.secrets["connections"]["supabase"]
            st.session_state["conn"] = psycopg2.connect(
                host=supabase["host"],
                port=supabase["port"],
                dbname=supabase["dbname"],
                user=supabase["user"],
                password=supabase["password"]
            )
            st.success("✅ Conexão com o banco de dados OK!")
        except Exception as e:
            st.error(f"❌ Erro ao conectar ao banco: {e}")
            return None
    return st.session_state["conn"]
    print("✅ Conexão OK!")
except Exception as e:
    print("❌ Erro:", e)
