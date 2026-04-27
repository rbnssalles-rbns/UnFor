#!/usr/bin/env python
# coding: utf-8

# In[ ]:


# BLOCO 1 — Chaves e utilitários
import os, time, math
import numpy as np, pandas as pd
import streamlit as st, pydeck as pdk
import openrouteservice
from geopy.geocoders import OpenCage

API_KEY_ORS = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjI5ZTlmZjk3ZTg4MzZjZGM1MDc3ZjBlMjNjOWMyYWU5YjM4ZTNhNzFjYTU4YzYxYjRhM2FmNjY0IiwiaCI6Im11cm11cjY0In0="
API_KEY_OPENCAGE = "480d28fce0a04bd4839c8cc832201807"

try:
    CLIENT_ORS = openrouteservice.Client(key=API_KEY_ORS)
except Exception as e:
    CLIENT_ORS = None
    st.warning(f"Falha ao inicializar OpenRouteService: {e}")

CLIENT_OPENCAGE = OpenCage(api_key=API_KEY_OPENCAGE, timeout=5)

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R*c

def geocode_endereco_com_fallback(endereco, lat_default=-3.73, lon_default=-38.54):
    try:
        if not endereco or str(endereco).strip() == "":
            return lat_default, lon_default, "Estimado"
        location = CLIENT_OPENCAGE.geocode(endereco)
        if location:
            return location.latitude, location.longitude, "OK"
        else:
            return lat_default, lon_default, "Estimado"
    except Exception:
        return lat_default, lon_default, "Estimado"

# BLOCO 2 — Importação da base única

st.sidebar.header("📂 Importar base única")
arquivo_base = st.sidebar.file_uploader("Base de solicitações (.xlsx)", type=["xlsx"])

df_base = None
if arquivo_base:
    df_base = pd.read_excel(arquivo_base)
    df_base.columns = [c.strip().upper() for c in df_base.columns]

    if "ABERTURA" in df_base.columns:
        df_base["ABERTURA"] = pd.to_datetime(df_base["ABERTURA"], errors="coerce", dayfirst=True)
        df_base["ABERTURA_DATA"] = df_base["ABERTURA"].dt.date
    else:
        st.error("Coluna 'ABERTURA' não encontrada no arquivo.")
        st.stop()

    st.success(f"{len(df_base)} registros carregados, datas convertidas.")
# BLOCO 3 — Filtros, ordenação e rota real

df_filtrado = pd.DataFrame()

if df_base is not None and "ABERTURA_DATA" in df_base.columns:
    dia_escolhido = st.sidebar.date_input("Escolha a data da solicitação")
    if dia_escolhido:
        df_filtrado = df_base[df_base["ABERTURA_DATA"] == dia_escolhido].copy()

if not df_filtrado.empty:
    st.subheader("🗺️ Rota das solicitações")

    # Preparar pontos a partir dos endereços geocodificados
    pontos = df_filtrado.dropna(subset=["LAT_DESTINO","LON_DESTINO"]).apply(
        lambda r: {"lat": float(r["LAT_DESTINO"]),
                   "lon": float(r["LON_DESTINO"]),
                   "name": str(r["SOLICITANTE"])}, axis=1
    ).tolist()

    # Função vizinho mais próximo
    def ordenar_vizinho_mais_proximo(orig_lat, orig_lon, pontos):
        rota = []
        atual_lat, atual_lon = orig_lat, orig_lon
        restantes = pontos.copy()
        while restantes:
            candidatos = [(p, haversine_km(atual_lat, atual_lon, p["lat"], p["lon"])) for p in restantes]
            prox, _ = min(candidatos, key=lambda x: x[1])
            rota.append(prox)
            atual_lat, atual_lon = prox["lat"], prox["lon"]
            restantes.remove(prox)
        return rota

    # Origem fixa (exemplo CD Fortaleza)
    origem_lat, origem_lon = -3.831753, -38.613147
    rota_ordenada = ordenar_vizinho_mais_proximo(origem_lat, origem_lon, pontos)
    pontos_sequencia = [{"lat": origem_lat, "lon": origem_lon, "name": "Centro de Distribuição"}] + rota_ordenada

    # Escolha de cor dos marcadores
    st.sidebar.header("🎨 Configurações do mapa")
    cor_opcao = st.sidebar.selectbox("Cor dos clientes", ["Azul","Verde","Laranja","Roxo","Cinza"])
    cores = {
        "Azul": [0,122,255,160],
        "Verde": [0,200,0,160],
        "Laranja": [255,140,0,160],
        "Roxo": [128,0,128,160],
        "Cinza": [128,128,128,160]
    }
    cor_marcador = cores[cor_opcao]

    # Calcular rota real via ORS
    rota_caminho, resumo = gerar_rota_real(pontos_sequencia)

    # Camadas do mapa
    icon_layer = pdk.Layer("ScatterplotLayer", data=pontos_sequencia,
                           get_position='[lon, lat]', get_radius=60,
                           get_fill_color=cor_marcador, pickable=True)
    path_layer = pdk.Layer("PathLayer",
                           data=[{"path": [[p["lon"], p["lat"]] for p in rota_caminho], "name": "Rota"}],
                           get_path="path", get_width=4, get_color=[0, 128, 255], width_min_pixels=2)

    # Estado inicial da visualização
    view_state = pdk.ViewState(latitude=origem_lat, longitude=origem_lon, zoom=11)

    # Renderizar mapa com marcadores + rota
    st.pydeck_chart(pdk.Deck(layers=[icon_layer, path_layer],
                             initial_view_state=view_state,
                             tooltip={"text": "{name}"}))

    # Indicadores da rota
    if resumo:
        total_min = int(resumo.get("duration", 0) / 60)
        total_km = round(resumo.get("distance", 0) / 1000, 2)
        c1, c2 = st.columns(2)
        c1.metric("Tempo total estimado", f"{total_min:.0f} min")
        c2.metric("Distância total", f"{total_km:.2f} km")
else:
    st.info("Nenhum registro encontrado ou base não carregada.")

# BLOCO 4 — Indicadores
if not df_filtrado.empty:
    tempo_total = pd.to_numeric(df_filtrado["TEMPO MEDIO ESPERA"], errors="coerce").sum()
    km_total = pd.to_numeric(df_filtrado["KM"], errors="coerce").sum()
    valor_total = pd.to_numeric(df_filtrado["VALOR TOTAL"], errors="coerce").sum()
    avaliacao_media = pd.to_numeric(df_filtrado["AVALIAÇÃO DO ATENDIMENTO"], errors="coerce").mean()

    st.subheader("📊 Indicadores da jornada")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tempo total", f"{tempo_total:.0f} min")
    c2.metric("Distância total", f"{km_total:.2f} km")
    c3.metric("Valor total", f"R$ {valor_total:.2f}")
    c4.metric("Avaliação média", f"{avaliacao_media:.1f}")
# BLOCO 5 — Exportação
st.sidebar.header("💾 Exportar resultados")
if not df_filtrado.empty:
    nome_arquivo = f"jornada_{dia_escolhido.strftime('%Y%m%d')}.csv"
    st.sidebar.download_button(
        label="Exportar jornada para CSV",
        data=df_filtrado.to_csv(index=False, encoding="utf-8-sig"),
        file_name=nome_arquivo,
        mime="text/csv"
    )
# BLOCO 6 — Importação de rotas já geradas (cache) com Resumo Final

import os
import pandas as pd

CACHE_DIR = "rotas_cache"   # pasta onde ficam os arquivos já gerados

st.sidebar.header("📂 Importar rotas já geradas")

def adicionar_resumo(df_cache):
    colunas_didaticas = [
        "ORIGEM","DESTINO EFETIVO","TEMPO MEDIO ESPERA",
        "KM","VALOR TOTAL","AVALIAÇÃO DO ATENDIMENTO"
    ]

    # Reordenar colunas conforme disponíveis
    df_cache = df_cache[[c for c in colunas_didaticas if c in df_cache.columns]]

    # Calcular totais
    tempo_total = df_cache["TEMPO MEDIO ESPERA"].sum() if "TEMPO MEDIO ESPERA" in df_cache.columns else 0
    km_total = df_cache["KM"].sum() if "KM" in df_cache.columns else 0
    valor_total = df_cache["VALOR TOTAL"].sum() if "VALOR TOTAL" in df_cache.columns else 0
    avaliacao_media = df_cache["AVALIAÇÃO DO ATENDIMENTO"].mean() if "AVALIAÇÃO DO ATENDIMENTO" in df_cache.columns else None
    pontos_rota_total = len(df_cache["DESTINO EFETIVO"].dropna().unique()) if "DESTINO EFETIVO" in df_cache.columns else 0

    # Linha de resumo
    linha_resumo = {
        "ORIGEM": "—",
        "DESTINO EFETIVO": "Resumo Final",
        "TEMPO MEDIO ESPERA": tempo_total,
        "KM": km_total,
        "VALOR TOTAL": valor_total,
        "AVALIAÇÃO DO ATENDIMENTO": round(avaliacao_media,1) if avaliacao_media else None,
        "Total de pontos na rota": pontos_rota_total
    }

    df_cache = pd.concat([df_cache, pd.DataFrame([linha_resumo])], ignore_index=True)
    return df_cache

# Botão para importar todos os arquivos salvos
if st.sidebar.button("Importar todas as rotas salvas"):
    if not os.path.exists(CACHE_DIR):
        st.warning("Nenhuma pasta de cache encontrada.")
    else:
        arquivos = [f for f in os.listdir(CACHE_DIR) if f.endswith(".xlsx")]
        if not arquivos:
            st.warning("Nenhum arquivo de rota salvo encontrado.")
        else:
            for arq in sorted(arquivos):
                caminho = os.path.join(CACHE_DIR, arq)
                try:
                    df_cache = pd.read_excel(caminho)
                    df_cache = adicionar_resumo(df_cache)
                    st.subheader(f"📄 {arq}")
                    st.dataframe(df_cache, use_container_width=True)
                except Exception as e:
                    st.error(f"Erro ao importar {arq}: {e}")

