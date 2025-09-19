import streamlit as st

# Conexão usando o pooler (6543)
conn = st.connection("supabase", type="sql")

try:
    df = conn.query("SELECT NOW();", ttl="0m")
    st.success("✅ Conexão bem-sucedida com o Supabase (PgBouncer 6543)!")
    st.write(df)
except Exception as e:
    st.error("❌ Erro na conexão com o Supabase")
    st.exception(e)
