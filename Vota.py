import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta

MIN_VOTOS = 2
TEMPO_MINUTOS = 10

def get_connection():
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
        except Exception as e:
            st.error(f"Erro ao conectar ao banco: {e}")
            return None
    return st.session_state["conn"]
# ... restante do código ...
