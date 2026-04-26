#!/usr/bin/env python
# coding: utf-8

# In[4]:


import streamlit as st
import pandas as pd
import numpy as np
import time
import math
import requests
import openrouteservice
import pydeck as pdk
from opencage.geocoder import OpenCageGeocode



# -------------------------------
# Chaves de API
# -------------------------------
API_KEY_ORS = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjI5ZTlmZjk3ZTg4MzZjZGM1MDc3ZjBlMjNjOWMyYWU5YjM4ZTNhNzFjYTU4YzYxYjRhM2FmNjY0IiwiaCI6Im11cm11cjY0In0="
API_KEY_OPENCAGE = "480d28fce0a04bd4839c8cc832201807"

try:
    CLIENT_ORS = openrouteservice.Client(key=API_KEY_ORS)
except Exception as e:
    CLIENT_ORS = None
    st.warning(f"Falha ao inicializar OpenRouteService: {e}")

# -------------------------------
# Utilitários
# -------------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def parse_float_or_none(s):
    try:
        return float(str(s).strip())
    except Exception:
        return None

# -------------------------------
# Aparência
# -------------------------------
st.sidebar.header("🎨 Aparência do mapa")
icon_size = st.sidebar.slider("Tamanho do marcador (1–8)", min_value=1, max_value=8, value=4)
size_scale = st.sidebar.slider("Escala do marcador (5–30)", min_value=5, max_value=30, value=15)

color_option = st.sidebar.selectbox(
    "Cor dos clientes",
    ["Azul", "Verde", "Laranja", "Roxo", "Cinza"]
)

marker_urls = {
    "Azul":   "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png",
    "Verde":  "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png",
    "Laranja":"https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-orange.png",
    "Roxo":   "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-violet.png",
    "Cinza":  "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-grey.png",
}
client_marker_url = marker_urls[color_option]
cd_marker_url = "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png"

st.markdown("<h1> Mapa de Rotas Programadas </h1>", unsafe_allow_html=True)

# -------------------------------
# Centro de Distribuição
# -------------------------------
st.sidebar.header("📍 Matrix de Distribuição")
cd_endereco = st.sidebar.text_input(
    "Endereço do Centro de Distribuição",
    "Av. Santos Dumont, 949 - Centro, Fortaleza - CE"
)

def geocode_opencage(endereco):
    geolocator = OpenCageGeocode(API_KEY_OPENCAGE)
    try:
        if not endereco or str(endereco).strip() == "":
            return None, None
        location = geolocator.geocode(endereco)
        if location and len(location) > 0:
            lat = location[0]['geometry']['lat']
            lon = location[0]['geometry']['lng']
            return lat, lon
        return None, None
    except Exception as e:
        st.warning(f"Erro na geocodificação do CD: {e}")
        return None, None

cd_lat, cd_lon = geocode_opencage(cd_endereco)

# Fallback manual
st.sidebar.markdown("### Coordenadas do CD (fallback manual)")
cd_coord_manual = st.sidebar.text_input(
    "Coordenadas do CD (lat, lon)",
    value=f"{cd_lat:.6f}, {cd_lon:.6f}" if cd_lat and cd_lon else ""
)

usar_manual = st.sidebar.checkbox(
    "Usar coordenadas manuais do CD",
    value=(cd_lat is None or cd_lon is None)
)

if usar_manual and cd_coord_manual:
    try:
        lat_str, lon_str = cd_coord_manual.split(",")
        cd_lat = parse_float_or_none(lat_str)
        cd_lon = parse_float_or_none(lon_str)
    except Exception:
        cd_lat, cd_lon = None, None

if cd_lat is not None and cd_lon is not None and (-90 <= cd_lat <= 90) and (-180 <= cd_lon <= 180):
    st.sidebar.success(f"CD localizado: {cd_lat:.6f}, {cd_lon:.6f}")
else:
    st.sidebar.error("Não foi possível definir o CD.")
# -------------------------------
# Upload de clientes
# -------------------------------
st.sidebar.header("📂 Importar clientes (.xlsx)")
arquivo = st.sidebar.file_uploader("Selecione um arquivo Excel", type=["xlsx"])

@st.cache_data
def geocode_dataframe_opencage(df, endereco_col="Endereco"):
    results = []
    geolocator = OpenCageGeocode(API_KEY_OPENCAGE)
    for _, row in df.iterrows():
        addr = str(row.get(endereco_col, "")).strip()
        if not addr:
            results.append((np.nan, np.nan))
            continue
        try:
            location = geolocator.geocode(addr)
            if location and len(location) > 0:
                lat = location[0]['geometry']['lat']
                lon = location[0]['geometry']['lng']
                results.append((lat, lon))
            else:
                results.append((np.nan, np.nan))
        except Exception:
            results.append((np.nan, np.nan))
        time.sleep(1)
    return results
# -------------------------------
# Função vizinho mais próximo
# -------------------------------
def vizinho_mais_proximo(cd_lat, cd_lon, pontos):
    nao_visitados = pontos.copy()
    ordem = []
    atual_lat, atual_lon = cd_lat, cd_lon

    while nao_visitados:
        prox = min(nao_visitados, key=lambda p: haversine_km(atual_lat, atual_lon, p["lat"], p["lon"]))
        ordem.append(prox)
        nao_visitados.remove(prox)
        atual_lat, atual_lon = prox["lat"], prox["lon"]

    return ordem

# -------------------------------
# Função para gerar rota real com ORS
# -------------------------------
def gerar_rota_real(cd_lat, cd_lon, pontos):
    if CLIENT_ORS is None or not pontos:
        return [], None, []
    coords = [[cd_lon, cd_lat]] + [[p["lon"], p["lat"]] for p in pontos]
    try:
        rota = CLIENT_ORS.directions(
            coordinates=coords,
            profile='driving-car',
            format='geojson'
        )
        caminho = rota['features'][0]['geometry']['coordinates']
        resumo = rota['features'][0]['properties']['summary']
        segmentos = rota['features'][0]['properties']['segments']
        return caminho, resumo, segmentos
    except Exception as e:
        st.warning(f"Erro ao gerar rota: {e}")
        return [], None, []

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
        coords = geocode_dataframe_opencage(df, endereco_col="Endereco")
    df["Latitude"], df["Longitude"] = zip(*coords)

    cores = [[255,0,0],[0,128,255],[0,200,0],[255,165,0],[128,0,128],[255,192,203],[0,255,255]]
    view_state = pdk.ViewState(latitude=cd_lat, longitude=cd_lon, zoom=11)

    rotas_disponiveis = df["Cliente"].unique().tolist()
    rota_selecionada = st.sidebar.selectbox("Selecione uma rota para visualizar", ["Todas"] + rotas_disponiveis)
    opcao = st.sidebar.radio("Escolha a simulação:", ["Ordem original", "Vizinho mais próximo"])

    layers, tabela_resumo, tabela_detalhada = [], [], []

    # Agrupamento por veículo + rota
    for i, ((cliente_id, rota_nome), grupo) in enumerate(df.groupby(["Cliente_ID","Cliente"])):
        if rota_selecionada != "Todas" and rota_nome != rota_selecionada:
            continue

        pontos = [
            {"lat": r["Latitude"], "lon": r["Longitude"], "name": f"Placa: {r['Cliente_ID']} | Rota: {r['Cliente']} | Endereço: {r['Endereco']}"}
            for _, r in grupo.iterrows() if not pd.isna(r["Latitude"]) and not pd.isna(r["Longitude"])
        ]
        if not pontos:
            continue

        pontos_ordenados = vizinho_mais_proximo(cd_lat, cd_lon, pontos) if opcao=="Vizinho mais próximo" else pontos
        caminho, resumo, segmentos = gerar_rota_real(cd_lat, cd_lon, pontos_ordenados)

        if resumo:
            dist_total = resumo.get("distance",0)/1000
            tempo_total_min = resumo.get("duration",0)/60
            horas, minutos = int(tempo_total_min//60), int(tempo_total_min%60)
            tabela_resumo.append({"Veículo": cliente_id,"Rota": rota_nome,"Distância Total (km)":f"{dist_total:.2f}","Tempo Total":f"{horas}h {minutos}min"})

            if isinstance(segmentos,list):
                origem="CD"
                for j,seg in enumerate(segmentos):
                    dist=seg["distance"]/1000
                    tempo_min=seg["duration"]/60
                    h,m=int(tempo_min//60),int(tempo_min%60)
                    tabela_detalhada.append({"Veículo":cliente_id,"Rota":rota_nome,"De":origem,"Para":f"Cliente {j+1}","Distância (km)":f"{dist:.2f}","Tempo":f"{h}h {m}min"})
                    origem=f"Cliente {j+1}"

        cor_rota = cores[i % len(cores)]

        path_layer = pdk.Layer("PathLayer",data=[{"path":caminho,"name":f"Rota {rota_nome} ({cliente_id})"}],
                               get_path="path",get_width=4,get_color=cor_rota,width_min_pixels=2)

        icon_data = [{"lat":cd_lat,"lon":cd_lon,"name":"Centro de Distribuição","icon":"cd","color":[255,0,0]}] + [
            {"lat":p["lat"],"lon":p["lon"],"name":p["name"],"icon":"cliente","color":cor_rota} for p in pontos_ordenados
        ]

        icon_layer = pdk.Layer("IconLayer",data=icon_data,get_icon="icon",get_size=icon_size,size_scale=size_scale,
                               get_position=["lon","lat"],get_color="color",pickable=True,
                               icon_atlas="https://raw.githubusercontent.com/visgl/deck.gl-data/master/website/icon-atlas.png",
                               icon_mapping={"cd":{"url":cd_marker_url,"width":128,"height":128,"anchorY":128},
                                             "cliente":{"url":client_marker_url,"width":128,"height":128,"anchorY":128}})

        layers.append(path_layer)
        layers.append(icon_layer)

    st.pydeck_chart(pdk.Deck(layers=layers,initial_view_state=view_state,tooltip={"text":"{name}"}))

    if tabela_resumo:
        st.markdown("### 📊 Resumo das Rotas")
        st.dataframe(pd.DataFrame(tabela_resumo))
    if tabela_detalhada:
        st.markdown("### 📍 Detalhamento De/Para")
        st.dataframe(pd.DataFrame(tabela_detalhada))

else:
    st.warning("Importe um arquivo Excel (.xlsx) com as colunas 'Cliente_ID','Cliente' e 'Endereco'.")


# In[ ]:





# In[ ]:




