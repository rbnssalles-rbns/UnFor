#!/usr/bin/env python
# coding: utf-8

# In[1]:


import streamlit as st
import pandas as pd
import numpy as np
import time
from geopy.geocoders import Nominatim
import requests
import openrouteservice
import pydeck as pdk

# -------------------------------
# Chaves de API
# -------------------------------
ORS_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjI5ZTlmZjk3ZTg4MzZjZGM1MDc3ZjBlMjNjOWMyYWU5YjM4ZTNhNzFjYTU4YzYxYjRhM2FmNjY0IiwiaCI6Im11cm11cjY0In0="
OPENCAGE_KEY = "480d28fce0a04bd4839c8cc832201807"

# -------------------------------
# Funções de geocodificação
# -------------------------------
def geocode(endereco):
    geolocator = Nominatim(user_agent="localizador_enderecos", timeout=10)
    try:
        location = geolocator.geocode(endereco)
        if location:
            return location.latitude, location.longitude
    except Exception:
        pass

    # Fallback para OpenCage
    try:
        url = "https://api.opencagedata.com/geocode/v1/json"
        params = {"q": endereco, "key": OPENCAGE_KEY, "language": "pt", "limit": 1}
        r = requests.get(url, params=params)
        data = r.json()
        if data.get("results"):
            lat = data["results"][0]["geometry"]["lat"]
            lon = data["results"][0]["geometry"]["lng"]
            return lat, lon
    except Exception:
        pass

    return None, None

def parse_origem(origem_input):
    # Se o usuário digitar coordenadas no formato "lat,lon"
    try:
        if "," in origem_input:
            lat_str, lon_str = origem_input.split(",")
            lat, lon = float(lat_str.strip()), float(lon_str.strip())
            return lat, lon
    except Exception:
        pass
    # Caso contrário, tratar como endereço
    return geocode(origem_input)

# -------------------------------
# Origem da rota (campo único)
# -------------------------------
st.sidebar.header("📍 Origem da rota")
origem_input = st.sidebar.text_input(
    "Digite a origem (endereço ou 'lat,lon')",
    "Travessa Francisco Marrocos Portela, Alto Alegre I, Maracanaú - CE, Brasil"
)

origem_lat, origem_lon = parse_origem(origem_input)

if origem_lat and origem_lon:
    st.sidebar.success(f"Origem definida: {origem_lat:.6f}, {origem_lon:.6f}")
else:
    st.sidebar.error("Não foi possível definir a origem.")

# -------------------------------
# Upload de clientes
# -------------------------------
st.sidebar.header("📂 Importar clientes (.xlsx)")
arquivo = st.sidebar.file_uploader("Selecione um arquivo Excel", type=["xlsx"])

st.title("📍 Localizador de Endereços e Rotas Reais")
st.write("Carregue um Excel com os clientes e endereços para geocodificar e traçar rotas reais a partir da origem definida.")

@st.cache_data
def geocode_dataframe(df, endereco_col="Endereco"):
    results = []
    for _, row in df.iterrows():
        addr = str(row.get(endereco_col, "")).strip()
        if not addr:
            results.append((np.nan, np.nan))
            continue
        lat, lon = geocode(addr)
        if lat and lon:
            results.append((lat, lon))
        else:
            results.append((np.nan, np.nan))
        time.sleep(1)  # respeitar limite de requisições
    return results

# -------------------------------
# Função para gerar rota real com ORS
# -------------------------------
def gerar_rota_real(origem_lat, origem_lon, pontos):
    client = openrouteservice.Client(key=ORS_KEY)
    # limitar a 50 pontos
    pontos = pontos[:50]
    coords = [[origem_lon, origem_lat]] + [[p["lon"], p["lat"]] for p in pontos]
    try:
        rota = client.directions(
            coordinates=coords,
            profile='driving-car',
            format='geojson'
        )
        caminho = rota['features'][0]['geometry']['coordinates']
        return [{"lon": lon, "lat": lat, "name": "Rota"} for lon, lat in caminho]
    except Exception as e:
        st.error(f"Erro ao gerar rota: {e}")
        return []

# -------------------------------
# Processamento do Excel
# -------------------------------
if arquivo:
    df = pd.read_excel(arquivo)
    df.columns = [c.strip() for c in df.columns]

    if "Cliente_ID" not in df.columns or "Endereco" not in df.columns:
        st.error("Arquivo inválido. É necessário conter as colunas 'Cliente_ID' e 'Endereco'.")
        st.stop()

    st.success(f"{len(df)} clientes carregados.")

    with st.spinner("Geocodificando endereços..."):
        coords = geocode_dataframe(df, endereco_col="Endereco")
    df["Latitude"], df["Longitude"] = zip(*coords)

    total = len(df)
    validos = df["Latitude"].notna().sum()
    st.info(f"Coordenadas obtidas para {validos}/{total} clientes.")

    # -------------------------------
    # Download dos resultados
    # -------------------------------
    st.subheader("📥 Baixar resultado geocodificado")
    st.dataframe(df.head(10))
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button("Baixar CSV geocodificado", data=csv_bytes, file_name="clientes_geocodificados.csv", mime="text/csv")

    # -------------------------------
    # Mapa e rota real
    # -------------------------------
    if origem_lat is not None and origem_lon is not None:
        st.subheader("🗺️ Mapa de clientes e rota real")
        pontos = [
            {"lat": r["Latitude"], "lon": r["Longitude"], "name": f"{r['Cliente_ID']} - {r['Cliente']}"}
            for _, r in df.iterrows() if not pd.isna(r["Latitude"]) and not pd.isna(r["Longitude"])
        ]

        rota = gerar_rota_real(origem_lat, origem_lon, pontos)
        path_data = [{
            "path": [[p["lon"], p["lat"]] for p in rota],
            "name": "Rota Origem -> Clientes"
        }]

        scatter = pdk.Layer(
            "ScatterplotLayer",
            data=pontos + [{"lat": origem_lat, "lon": origem_lon, "name": "Origem"}],
            get_position='[lon, lat]',
            get_fill_color='[255, 99, 71]',
            get_radius=60,
            pickable=True
        )
        path_layer = pdk.Layer(
            "PathLayer",
            data=path_data,
            get_path="path",
            get_width=4,
            get_color=[0, 128, 255],
            width_min_pixels=2
        )
        view_state = pdk.ViewState(latitude=origem_lat, longitude=origem_lon, zoom=11)
        st.pydeck_chart(pdk.Deck(layers=[scatter, path_layer], initial_view_state=view_state, tooltip={"text": "{name}"}))
    else:
        st.warning("Defina uma origem válida (endereço ou coordenadas).")
else:
    st.warning("Importe um arquivo Excel (.xlsx) com as colunas 'Cliente_ID', 'Cliente' e 'Endereco'.")


# In[ ]:




