import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os

st.set_page_config(
    page_title="Analisis de Permanencia",
    page_icon="📷",
    layout="wide"
)

st.title("📷 Analisis de Permanencia de Personas")
st.caption("Resultados generados por el modelo de deteccion con YOLOv8")

# ── Selector de archivo ───────────────────────────────────────────────────────
csv_default = "permanencia.csv"
uploaded = st.sidebar.file_uploader("Cargar otro CSV", type="csv")

if uploaded:
    df = pd.read_csv(uploaded)
    st.sidebar.success(f"Archivo cargado: {uploaded.name}")
elif os.path.exists(csv_default):
    df = pd.read_csv(csv_default)
    st.sidebar.info(f"Usando: {csv_default}")
else:
    st.error("No se encontro permanencia.csv. Ejecuta primero detectar_pau.py.")
    st.stop()

# ── Parseo de timestamps ──────────────────────────────────────────────────────
def parse_ts(ts_str):
    parts = str(ts_str).strip().split(":")
    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    return timedelta(hours=h, minutes=m, seconds=s)

base = datetime(2000, 1, 1)
df["inicio_dt"] = df["entrada"].apply(lambda x: base + parse_ts(x))
df["fin_dt"]    = df["salida"].apply(lambda x: base + parse_ts(x))
df["Persona"]   = df["id"].apply(lambda x: f"Persona {x:02d}")

# ── Filtros sidebar ───────────────────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.subheader("Filtros")
min_min = float(df["duracion_min"].min())
max_min = float(df["duracion_min"].max())
rango = st.sidebar.slider(
    "Permanencia (minutos)",
    min_value=min_min,
    max_value=max_min,
    value=(min_min, max_min),
    step=0.5
)
df_filtrado = df[(df["duracion_min"] >= rango[0]) & (df["duracion_min"] <= rango[1])]

# ── Metricas principales ──────────────────────────────────────────────────────
st.markdown("### Resumen")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Personas unicas",     len(df))
c2.metric("Filtradas (rango)",   len(df_filtrado))
c3.metric("Permanencia promedio", f"{df['duracion_min'].mean():.1f} min")
c4.metric("Mayor permanencia",   f"{df['duracion_min'].max():.1f} min")
c5.metric("Menor permanencia",   f"{df['duracion_min'].min():.1f} min")

st.divider()

# ── Graficos principales ──────────────────────────────────────────────────────
col_izq, col_der = st.columns([3, 2])

with col_izq:
    st.subheader("Linea de tiempo por persona")

    altura = max(400, len(df_filtrado) * 35)
    fig_gantt = px.timeline(
        df_filtrado.sort_values("inicio_dt"),
        x_start="inicio_dt",
        x_end="fin_dt",
        y="Persona",
        color="duracion_min",
        color_continuous_scale="Blues",
        labels={"duracion_min": "Minutos en escena"},
        hover_data={
            "entrada": True,
            "salida": True,
            "duracion_min": ":.1f",
            "inicio_dt": False,
            "fin_dt": False,
        }
    )
    fig_gantt.update_layout(
        xaxis_tickformat="%H:%M:%S",
        xaxis_title="Tiempo del video",
        yaxis={"autorange": "reversed", "title": ""},
        height=altura,
        coloraxis_colorbar={"title": "Min"},
        margin={"l": 10, "r": 10, "t": 10, "b": 40},
    )
    st.plotly_chart(fig_gantt, use_container_width=True)

with col_der:
    st.subheader("Distribucion de permanencia")

    def bucket(min_val):
        sec = min_val * 60
        if sec < 60:    return "< 1 min"
        if sec < 300:   return "1 - 5 min"
        if sec < 900:   return "5 - 15 min"
        if sec < 3600:  return "15 - 60 min"
        return "> 1 hora"

    orden = ["< 1 min", "1 - 5 min", "5 - 15 min", "15 - 60 min", "> 1 hora"]
    df["rango"] = df["duracion_min"].apply(bucket)
    conteo = df["rango"].value_counts().reindex(orden, fill_value=0).reset_index()
    conteo.columns = ["Rango", "Personas"]

    fig_dist = px.bar(
        conteo, x="Rango", y="Personas",
        color="Personas",
        color_continuous_scale="Blues",
        text="Personas"
    )
    fig_dist.update_traces(textposition="outside")
    fig_dist.update_layout(
        showlegend=False,
        coloraxis_showscale=False,
        xaxis_title="",
        height=350,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
    )
    st.plotly_chart(fig_dist, use_container_width=True)

    st.subheader("Personas por hora de entrada")
    df["hora_entrada"] = df["inicio_dt"].dt.hour
    por_hora = df.groupby("hora_entrada").size().reset_index(name="Personas")
    fig_hora = px.bar(
        por_hora, x="hora_entrada", y="Personas",
        labels={"hora_entrada": "Hora del video"},
        color="Personas",
        color_continuous_scale="Teal"
    )
    fig_hora.update_layout(
        coloraxis_showscale=False,
        height=280,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
    )
    st.plotly_chart(fig_hora, use_container_width=True)

st.divider()

# ── Tabla detallada ───────────────────────────────────────────────────────────
st.subheader("Detalle por persona")
tabla = df_filtrado[["id", "entrada", "salida", "duracion_min"]].copy()
tabla.columns = ["ID", "Entrada", "Salida", "Duracion (min)"]
tabla = tabla.sort_values("Duracion (min)", ascending=False).reset_index(drop=True)

st.dataframe(
    tabla.style.background_gradient(subset=["Duracion (min)"], cmap="Blues"),
    use_container_width=True,
    hide_index=True,
    height=min(600, (len(tabla) + 1) * 36)
)

csv_export = tabla.to_csv(index=False).encode("utf-8")
st.download_button(
    "⬇ Descargar tabla filtrada como CSV",
    csv_export,
    "permanencia_filtrada.csv",
    "text/csv"
)
