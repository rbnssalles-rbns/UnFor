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

# Função para obter rota real pelas ruas com ORS Directions
def get_route(coords):
    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    headers = {"Authorization": ORS_KEY, "Content-Type": "application/json"}
    body = {"coordinates": coords}
    r = requests.post(url, json=body, headers=headers)
    data = r.json()
    if "features" in data:
        return data["features"][0]["geometry"]["coordinates"]
    return []

# Função para otimização com ORS Optimization API
def optimize_routes(vehicles, jobs):
    url = "https://api.openrouteservice.org/optimization"
    headers = {"Authorization": ORS_KEY, "Content-Type": "application/json"}
    payload = {"vehicles": vehicles, "jobs": jobs}
    r = requests.post(url, json=payload, headers=headers)
    return r.json()

# Interface Streamlit
st.title("🚚 Rota Programada com Otimização Automática")

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

    # Escolha do método
    metodo = st.radio("📌 Escolha o método de rota:", 
                      ["Seguir ordem do arquivo", "Otimizar automaticamente (ORS VRP)"])

    # Criar mapa centralizado em Fortaleza
    m = folium.Map(location=[-3.730, -38.520], zoom_start=12)

    # Paleta de cores para rotas
    colors = ["red", "blue", "green", "purple", "orange", "darkred", "cadetblue"]

    if metodo == "Seguir ordem do arquivo":
        # Agrupar por veículo (Cliente_ID)
        for i, (placa, grupo) in enumerate(df.groupby("Cliente_ID")):
            cor = colors[i % len(colors)]
            coords = grupo[["Longitude", "Latitude"]].dropna().values.tolist()
            route = get_route(coords)

            # Adicionar marcadores
            for _, row in grupo.iterrows():
                if pd.notna(row["Latitude"]) and pd.notna(row["Longitude"]):
                    folium.Marker(
                        location=[row["Latitude"], row["Longitude"]],
                        popup=f"{row['Cliente']} - {row['Endereco']} ({row['DATA']})",
                        icon=folium.Icon(color=cor)
                    ).add_to(m)

            # Adicionar linha da rota real
            if route:
                folium.PolyLine([(lat, lon) for lon, lat in route], 
                                color=cor, weight=5, opacity=0.8,
                                tooltip=f"Placa {placa} - Rota {grupo['Cliente'].iloc[0]}").add_to(m)

    else:  # Otimização automática com ORS VRP
        vehicles = []
        jobs = []

        # Criar veículos dinamicamente
        for placa, grupo in df.groupby("Cliente_ID"):
            start = grupo[["Longitude", "Latitude"]].dropna().values.tolist()[0]
            vehicles.append({"id": str(placa), "start": start})

            # Criar jobs
            for idx, row in grupo.iterrows():
                if pd.notna(row["Latitude"]) and pd.notna(row["Longitude"]):
                    jobs.append({
                        "id": idx,
                        "location": [row["Longitude"], row["Latitude"]],
                        "description": f"{row['Cliente']} - {row['Endereco']} ({row['DATA']})"
                    })

        # Chamar ORS Optimization
        result = optimize_routes(vehicles, jobs)

        # Desenhar rotas otimizadas
        for i, route_data in enumerate(result.get("routes", [])):
            cor = colors[i % len(colors)]
            coords = route_data["steps"]
            ordered_coords = [step["location"] for step in coords if "location" in step]

            # Obter trajeto real
            route = get_route(ordered_coords)

            # Adicionar marcadores
            for step in coords:
                if "location" in step:
                    lon, lat = step["location"]
                    folium.Marker(
                        location=[lat, lon],
                        popup=step.get("description", ""),
                        icon=folium.Icon(color=cor)
                    ).add_to(m)

            # Adicionar linha da rota real
            if route:
                folium.PolyLine([(lat, lon) for lon, lat in route],
                                color=cor, weight=5, opacity=0.8,
                                tooltip=f"Rota otimizada {i+1}").add_to(m)

    # Exibir mapa no Streamlit
    st.write("📍 Rotas no mapa com cores distintas por veículo")
    st.components.v1.html(m._repr_html_(), height=600)


# In[ ]:




