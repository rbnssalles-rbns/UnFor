#!/usr/bin/env python
# coding: utf-8

# In[1]:


import streamlit as st
import pandas as pd
import requests
import folium

# Configurações das APIs
OPENCAGE_KEY = "480d28fce0a04bd4839c8cc832201807"
ORS_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjI5ZTlmZjk3ZTg4MzZjZGM1MDc3ZjBlMjNjOWMyYWU5YjM4ZTNhNzFjYTU4YzYxYjRhM2FmNjY0IiwiaCI6Im11cm11cjY0In0="

# Função para geocodificação com OpenCage
def geocode_opencage(endereco):
    url = "https://api.opencagedata.com/geocode/v1/json"
    params = {"q": endereco, "key": OPENCAGE_KEY, "language": "pt", "limit": 1}
    r = requests.get(url, params=params)
    data = r.json()
    if data["results"]:
        lat = data["results"][0]["geometry"]["lat"]
        lon = data["results"][0]["geometry"]["lng"]
        return (lat, lon)
    return None

# Função para matriz de distâncias com OpenRouteService
def distance_matrix(coords):
    url = "https://api.openrouteservice.org/v2/matrix/driving-car"
    headers = {"Authorization": ORS_KEY, "Content-Type": "application/json"}
    body = {"locations": coords, "metrics": ["distance", "duration"]}
    r = requests.post(url, json=body, headers=headers)
    return r.json()

# Interface Streamlit
st.title("🚚 Rota Programada")

# Upload do arquivo Excel
uploaded_file = st.file_uploader("📂 Envie o arquivo 'Rota Programada' (.xlsx)", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    st.success("✅ Arquivo carregado com sucesso!")
    st.dataframe(df)

    # Geocodificação dos endereços
    df["Coordenadas"] = df["Endereco"].apply(geocode_opencage)
    df["Latitude"] = df["Coordenadas"].apply(lambda x: x[0] if x else None)
    df["Longitude"] = df["Coordenadas"].apply(lambda x: x[1] if x else None)

    # Avisar se algum endereço não foi reconhecido
    enderecos_invalidos = df[df["Latitude"].isna()]["Endereco"].tolist()
    if enderecos_invalidos:
        st.warning(f"⚠️ Endereços não reconhecidos: {enderecos_invalidos}")

    # Criar mapa centralizado em Fortaleza
    m = folium.Map(location=[-3.730, -38.520], zoom_start=12)

    # Paleta de cores para rotas
    colors = ["red", "blue", "green", "purple", "orange", "darkred", "cadetblue"]

    # Agrupar por veículo (Cliente_ID)
    for i, (placa, grupo) in enumerate(df.groupby("Cliente_ID")):
        cor = colors[i % len(colors)]
        coords = grupo[["Latitude", "Longitude"]].dropna().values.tolist()

        # Adicionar marcadores
        for _, row in grupo.iterrows():
            if pd.notna(row["Latitude"]) and pd.notna(row["Longitude"]):
                folium.Marker(
                    location=[row["Latitude"], row["Longitude"]],
                    popup=f"{row['Cliente']} - {row['Endereco']} ({row['DATA']})",
                    icon=folium.Icon(color=cor)
                ).add_to(m)

        # Adicionar linha conectando pontos da rota
        if coords:
            folium.PolyLine(coords, color=cor, weight=4, opacity=0.7,
                            tooltip=f"Placa {placa} - Rota {grupo['Cliente'].iloc[0]}").add_to(m)

    # Exibir mapa no Streamlit
    st.write("📍 Rotas no mapa com cores distintas por veículo")
    st.components.v1.html(m._repr_html_(), height=600)


# In[ ]:




