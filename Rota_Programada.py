#!/usr/bin/env python
# coding: utf-8

# In[1]:


import streamlit as st
import pandas as pd
import requests
import folium

# Configurações das APIs
OPENCAGE_KEY = "SUA_CHAVE_OPENCAGE"
ORS_KEY = "SUA_CHAVE_OPENROUTESERVICE"

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

# Função para obter trajeto real pelas ruas com ORS Directions
def get_route(coords):
    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    headers = {"Authorization": ORS_KEY, "Content-Type": "application/json"}
    body = {"coordinates": coords}
    r = requests.post(url, json=body, headers=headers)
    data = r.json()
    if "features" in data:
        return [(lat, lon) for lon, lat in data["features"][0]["geometry"]["coordinates"]]
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

uploaded_file = st.file_uploader("📂 Envie o arquivo 'Rota Programada' (.xlsx)", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    st.success("✅ Arquivo carregado com sucesso!")
    st.dataframe(df)

    # Geocodificação
    df["Coordenadas"] = df["Endereco"].apply(geocode_opencage)
    df["Latitude"] = df["Coordenadas"].apply(lambda x: x[0] if x else None)
    df["Longitude"] = df["Coordenadas"].apply(lambda x: x[1] if x else None)

    enderecos_invalidos = df[df["Latitude"].isna()]["Endereco"].tolist()
    if enderecos_invalidos:
        st.warning(f"⚠️ Endereços não reconhecidos: {enderecos_invalidos}")

    metodo = st.radio("📌 Escolha o método de rota:", 
                      ["Seguir ordem do arquivo", "Otimizar automaticamente (ORS VRP)"])

    m = folium.Map(location=[-3.730, -38.520], zoom_start=12)
    colors = ["red", "blue", "green", "purple", "orange", "darkred", "cadetblue"]

    if metodo == "Seguir ordem do arquivo":
        for i, (placa, grupo) in enumerate(df.groupby("Cliente_ID")):
            cor = colors[i % len(colors)]
            coords = grupo[["Longitude", "Latitude"]].dropna().values.tolist()
            route = get_route(coords)

            for _, row in grupo.iterrows():
                if pd.notna(row["Latitude"]) and pd.notna(row["Longitude"]):
                    folium.Marker(
                        location=[row["Latitude"], row["Longitude"]],
                        popup=f"{row['Cliente']} - {row['Endereco']} ({row['DATA']})",
                        icon=folium.Icon(color=cor)
                    ).add_to(m)

            if route:
                folium.PolyLine(route, color=cor, weight=5, opacity=0.8,
                                tooltip=f"Placa {placa}").add_to(m)

    else:  # Otimização automática
        vehicles, jobs = [], []

        for placa, grupo in df.groupby("Cliente_ID"):
            start = grupo[["Longitude", "Latitude"]].dropna().values.tolist()[0]
            vehicles.append({"id": str(placa), "start": start})

            for idx, row in grupo.iterrows():
                if pd.notna(row["Latitude"]) and pd.notna(row["Longitude"]):
                    jobs.append({
                        "id": idx,
                        "location": [row["Longitude"], row["Latitude"]],
                        "description": f"{row['Cliente']} - {row['Endereco']} ({row['DATA']})"
                    })

        result = optimize_routes(vehicles, jobs)

        for i, route_data in enumerate(result.get("routes", [])):
            cor = colors[i % len(colors)]
            ordered_coords = [step["location"] for step in route_data["steps"] if "location" in step]

            # Chamar Directions API com a ordem otimizada
            route = get_route(ordered_coords)

            for step in route_data["steps"]:
                if "location" in step:
                    lon, lat = step["location"]
                    folium.Marker(
                        location=[lat, lon],
                        popup=step.get("description", ""),
                        icon=folium.Icon(color=cor)
                    ).add_to(m)

            if route:
                folium.PolyLine(route, color=cor, weight=5, opacity=0.8,
                                tooltip=f"Rota otimizada {i+1}").add_to(m)

    st.write("📍 Rotas no mapa com cores distintas por veículo")
    st.components.v1.html(m._repr_html_(), height=600)


# In[ ]:




