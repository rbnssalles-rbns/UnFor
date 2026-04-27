#!/usr/bin/env python
# coding: utf-8

# In[2]:


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

# -------------------------------
# Função vizinho mais próximo robusta
# -------------------------------
def vizinho_mais_proximo(cd_lat, cd_lon, pontos):
    nao_visitados = [p for p in pontos if p["lat"] is not None and p["lon"] is not None]
    ordem = []
    atual_lat, atual_lon = cd_lat, cd_lon

    while nao_visitados:
        prox = min(
            nao_visitados,
            key=lambda p: haversine_km(float(atual_lat), float(atual_lon),
                                       float(p["lat"]), float(p["lon"]))
        )
        ordem.append(prox)
        nao_visitados.remove(prox)
        atual_lat, atual_lon = prox["lat"], prox["lon"]

    return ordem

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

st.markdown("<h1>📍 Rotas Programadas </h1>", unsafe_allow_html=True)

# -------------------------------
# Centro de Distribuição
# -------------------------------
st.sidebar.header("📍 Centro de distribuição")
cd_endereco = st.sidebar.text_input(
    "Endereço do Centro de Distribuição",
    "Av. Santos Dumont, 949 - Aldeota, Fortaleza - CE,"
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

    # Avisar sobre clientes sem coordenadas
    clientes_invalidos = df[df["Latitude"].isna() | df["Longitude"].isna()][["Cliente_ID","Cliente","Endereco"]]
    if not clientes_invalidos.empty:
        st.warning("Clientes sem coordenadas válidas (não entram nas rotas):")
        st.write(clientes_invalidos)

    cores = [[255,0,0],[0,128,255],[0,200,0],[255,165,0],[128,0,128],[255,192,203],[0,255,255]]
    view_state = pdk.ViewState(latitude=cd_lat, longitude=cd_lon, zoom=11)

    # Criar lista de opções de filtro (placa + rota)
    opcoes_rotas = [f"{cid} - {rota}" for cid, rota in df.groupby(["Cliente_ID","Cliente"]).groups.keys()]
    rota_selecionada = st.sidebar.selectbox("Selecione uma rota para visualizar", ["Todas"] + opcoes_rotas)

    layers = []
    tabela_resumo = []
    tabela_detalhada = []

    # Loop por veículo + rota
    for i, ((cliente_id, rota_nome), grupo) in enumerate(df.groupby(["Cliente_ID","Cliente"])):
        chave = f"{cliente_id} - {rota_nome}"
        if rota_selecionada != "Todas" and rota_selecionada != chave:
            continue

        # Sanitização dos pontos
        pontos = [
            {
                "lat": float(r["Latitude"]),
                "lon": float(r["Longitude"]),
                "name": f"Placa: {r['Cliente_ID']} | Rota: {r['Cliente']} | Endereço: {r['Endereco']}"
            }
            for _, r in grupo.iterrows()
            if pd.notna(r["Latitude"]) and pd.notna(r["Longitude"])
        ]
        if not pontos:
            continue

                # Ordenar clientes pelo vizinho mais próximo
        pontos_ordenados = vizinho_mais_proximo(cd_lat, cd_lon, pontos)

        caminho, resumo, segmentos = gerar_rota_real(cd_lat, cd_lon, pontos_ordenados)

        if resumo:
            dist_total = resumo.get("distance", 0) / 1000
            tempo_total_min = resumo.get("duration", 0) / 60
            horas = int(tempo_total_min // 60)
            minutos = int(tempo_total_min % 60)
            tempo_formatado = f"{horas}h {minutos}min"

            tabela_resumo.append({
                "Veículo": cliente_id,
                "Rota": rota_nome,
                "Data": grupo["DATA"].iloc[0] if "DATA" in grupo.columns else "",
                "Distância Total (km)": f"{dist_total:.2f}",
                "Tempo Total": tempo_formatado
            })

            # Tabela detalhada De/Para
            if isinstance(segmentos, list):
                origem = "CD"
                for j, seg in enumerate(segmentos):
                    dist = seg["distance"] / 1000
                    tempo_min = seg["duration"] / 60
                    h = int(tempo_min // 60)
                    m = int(tempo_min % 60)
                    tempo_seg = f"{h}h {m}min"

                    destino = f"Cliente {j+1}"
                    tabela_detalhada.append({
                        "Veículo": cliente_id,
                        "Rota": rota_nome,
                        "Data": grupo["DATA"].iloc[0] if "DATA" in grupo.columns else "",
                        "De": origem,
                        "Para": destino,
                        "Distância (km)": f"{dist:.2f}",
                        "Tempo": tempo_seg
                    })
                    origem = destino

        # Cor da rota e dos marcadores
        cor_rota = cores[i % len(cores)]

        # Camada da rota
        path_data = [{
            "path": caminho,
            "name": f"Rota {rota_nome} ({cliente_id})"
        }]
        path_layer = pdk.Layer(
            "PathLayer",
            data=path_data,
            get_path="path",
            get_width=4,
            get_color=cor_rota,
            width_min_pixels=2
        )

        # Dados dos ícones (CD + clientes)
        icon_data = [
            {"lat": cd_lat, "lon": cd_lon, "name": "Centro de Distribuição", "icon": "cd", "color": [255,0,0]}
        ] + [
            {"lat": p["lat"], "lon": p["lon"], "name": p["name"], "icon": "cliente", "color": cor_rota}
            for p in pontos_ordenados
        ]

        icon_layer = pdk.Layer(
            "IconLayer",
            data=icon_data,
            get_icon="icon",
            get_size=icon_size,
            size_scale=size_scale,
            get_position=["lon", "lat"],
            get_color="color",
            pickable=True,
            icon_atlas="https://raw.githubusercontent.com/visgl/deck.gl-data/master/website/icon-atlas.png",
            icon_mapping={
                "cd": {"x": 0, "y": 0, "width": 128, "height": 128,
                       "anchorY": 128, "mask": True, "url": cd_marker_url},
                "cliente": {"x": 0, "y": 0, "width": 128, "height": 128,
                            "anchorY": 128, "mask": True, "url": client_marker_url}
            }
        )

        layers.extend([path_layer, icon_layer])

    # Renderização do mapa
    st.pydeck_chart(
        pdk.Deck(
            layers=layers,
            initial_view_state=view_state,
            tooltip={"text": "{name}"}
        )
    )

    # Tabelas organizadas abaixo do mapa
    if tabela_resumo:
        st.markdown("### 📊 Resumo das Rotas")
        st.dataframe(pd.DataFrame(tabela_resumo))

    if tabela_detalhada:
        st.markdown("### 📍 Detalhamento De/Para")
        st.dataframe(pd.DataFrame(tabela_detalhada))

else:
    st.warning("Importe um arquivo Excel (.xlsx) com as colunas 'Cliente_ID', 'Cliente' e 'Endereco'.")


# In[ ]:





# In[ ]:




