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
    try:
        if "," in origem_input:
            lat_str, lon_str = origem_input.split(",")
            lat, lon = float(lat_str.strip()), float(lon_str.strip())
            return lat, lon
    except Exception:
        pass
    return geocode(origem_input)

# -------------------------------
# Origem da rota (campo único)
# -------------------------------
st.sidebar.header("📍 Origem da rota")
origem_input = st.sidebar.text_input(
    "Digite a origem (endereço ou 'lat,lon')",
    "Travessa Francisco Marrocos Portela, Alto Alegre I, Maracanaú - CE, Brasil"
)
otimizar = st.sidebar.checkbox("Otimizar rota automaticamente (TSP)")

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
        time.sleep(1)
    return results

# -------------------------------
# Função para gerar rota real com ORS
# -------------------------------
def gerar_rota_real(origem_lat, origem_lon, pontos, otimizar=False):
    client = openrouteservice.Client(key=ORS_KEY)
    pontos = pontos[:50]
    coords = [[origem_lon, origem_lat]] + [[p["lon"], p["lat"]] for p in pontos]
    try:
        if otimizar:
            # Usar endpoint de otimização
            jobs = []
            for idx, p in enumerate(coords[1:], start=1):
                jobs.append({"id": idx, "location": p})
            vehicles = [{"id": 1, "start": coords[0]}]
            rota = client.optimization(jobs=jobs, vehicles=vehicles)
            caminho = rota['routes'][0]['geometry']
            summary = rota['routes'][0]['summary']
            segments = rota['routes'][0]['steps']
        else:
            rota = client.directions(
                coordinates=coords,
                profile='driving-car',
                format='geojson'
            )
            caminho = rota['features'][0]['geometry']['coordinates']
            summary = rota['features'][0]['properties']['summary']
            segments = rota['features'][0]['properties']['segments']
        return caminho, summary, segments
    except Exception as e:
        st.error(f"Erro ao gerar rota: {e}")
        return [], {}, []

# -------------------------------
# Processamento do Excel
# -------------------------------
if arquivo:
    df = pd.read_excel(arquivo)
    df.columns = [c.strip() for c in df.columns]

    if "Cliente_ID" not in df.columns or "Cliente" not in df.columns or "Endereco" not in df.columns:
        st.error("Arquivo inválido. É necessário conter as colunas 'Cliente_ID', 'Cliente' e 'Endereco'.")
        st.stop()

    with st.spinner("Geocodificando endereços..."):
        coords = geocode_dataframe(df, endereco_col="Endereco")
    df["Latitude"], df["Longitude"] = zip(*coords)

    # -------------------------------
    # Seletor de rotas
    # -------------------------------
    rotas_disponiveis = df["Cliente"].unique().tolist()
    rota_selecionada = st.sidebar.selectbox("Escolha a rota para visualizar", ["Todas"] + rotas_disponiveis)

    cores = [[255,0,0],[0,128,255],[0,200,0],[255,165,0],[128,0,128],[255,192,203],[0,255,255]]
    layers = []
    view_state = pdk.ViewState(latitude=origem_lat, longitude=origem_lon, zoom=11)

    # Agrupamento por veículo e rota
    for i, ((cliente_id, rota_nome), grupo) in enumerate(df.groupby(["Cliente_ID","Cliente"])):
        if rota_selecionada != "Todas" and rota_nome != rota_selecionada:
            continue

        pontos = [
            {"lat": r["Latitude"], "lon": r["Longitude"], "name": f"Placa: {r['Cliente_ID']} | Rota: {r['Cliente']} | Endereço: {r['Endereco']}"}
            for _, r in grupo.iterrows() if not pd.isna(r["Latitude"]) and not pd.isna(r["Longitude"])
        ]
        if not pontos:
            continue

        caminho, summary, segments = gerar_rota_real(origem_lat, origem_lon, pontos, otimizar=otimizar)

        dist_total = summary.get("distance",0)/1000
        tempo_total = summary.get("duration",0)/60
        st.markdown(f"**Veículo {cliente_id} | Rota {rota_nome}** — Distância total: {dist_total:.2f} km | Tempo total: {tempo_total:.1f} min")

        # Mostrar tempos/distâncias por trecho
        if isinstance(segments, list):
            for j, seg in enumerate(segments):
                if "distance" in seg and "duration" in seg:
                    dist = seg["distance"]/1000
                    tempo = seg["duration"]/60
                    st.write(f"Trecho {j+1}: {dist:.2f} km | {tempo:.1f} min")

        path_data = [{"path": caminho, "name": f"Rota {rota_nome} ({cliente_id})"}]
        path_layer = pdk.Layer(
            "PathLayer",
            data=path_data,
            get_path="path",
            get_width=4,
            get_color=cores[i % len(cores)],
            width_min_pixels=2
        )
        scatter = pdk.Layer(
            "ScatterplotLayer",
            data=pontos + [{"lat": origem_lat, "lon": origem_lon, "name": "Origem"}],
            get_position='[lon, lat]',
            get_fill_color=cores[i % len(cores)],
            get_radius=80,
            pickable=True
        )
        layers.extend([path_layer, scatter])

    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view_state, tooltip={"text": "{name}"}))
else:
    st.warning("Importe um arquivo Excel (.xlsx) com as colunas 'Cliente_ID', 'Cliente' e 'Endereco'.")


# In[ ]:




