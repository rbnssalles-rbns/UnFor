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

# BLOCO 2 — Importação da base única (revisado com conversão de datas e extração da parte da data)

st.sidebar.header("📂 Importar base única")
arquivo_base = st.sidebar.file_uploader("Base de solicitações (.xlsx)", type=["xlsx"])

df_base = None
if arquivo_base:
    df_base = pd.read_excel(arquivo_base)
    df_base.columns = [c.strip().upper() for c in df_base.columns]

    # Converter coluna ABERTURA para datetime
    df_base["ABERTURA"] = pd.to_datetime(df_base["ABERTURA"], errors="coerce", dayfirst=True)

    # Extrair apenas a parte da data (descartando hora)
    df_base["ABERTURA_DATA"] = df_base["ABERTURA"].dt.date

    # Validar colunas obrigatórias
    col_obrig = [
        "ABERTURA","SOLICITANTE","ORIGEM","DESTINO EFETIVO",
        "TEMPO MEDIO ESPERA","KM","PREFIXO","MODELO",
        "MOTORISTA","VALOR TOTAL","AVALIAÇÃO DO ATENDIMENTO"
    ]
    faltantes = [c for c in col_obrig if c not in df_base.columns]
    if faltantes:
        st.error(f"Arquivo inválido. Faltam colunas: {', '.join(faltantes)}")
        st.stop()

    # Geocodificação com fallback
    df_base[["LAT_ORIGEM","LON_ORIGEM","STATUS_ORIGEM"]] = df_base["ORIGEM"].apply(
        lambda x: pd.Series(geocode_endereco_com_fallback(x))
    )
    df_base[["LAT_DESTINO","LON_DESTINO","STATUS_DESTINO"]] = df_base["DESTINO EFETIVO"].apply(
        lambda x: pd.Series(geocode_endereco_com_fallback(x))
    )

    st.success(f"{len(df_base)} registros carregados, datas convertidas e endereços geocodificados.")
# BLOCO 3 — Filtros e simulação (revisado e sem erros)

# Campo lateral para escolher a data
dia_escolhido = st.sidebar.date_input("Escolha a data da solicitação")

df_filtrado = pd.DataFrame()
if dia_escolhido:
    # Converter a data escolhida para Timestamp (mesmo tipo da coluna ABERTURA_DATA)
    dia_escolhido_ts = pd.to_datetime(dia_escolhido)

    # Filtrar registros pela data escolhida
    df_filtrado = df_base[df_base["ABERTURA_DATA"] == dia_escolhido_ts].copy()

if not df_filtrado.empty:
    st.subheader("🗺️ Mapa das solicitações")

    # Preparar pontos para o mapa
    pontos = df_filtrado.dropna(subset=["LAT_DESTINO","LON_DESTINO"]).apply(
        lambda r: {
            "lat": r["LAT_DESTINO"],
            "lon": r["LON_DESTINO"],
            "name": str(r["SOLICITANTE"])
        }, axis=1
    ).tolist()

    if pontos:
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=pontos,
            get_position='[lon, lat]',
            get_radius=60,
            get_fill_color=[0,122,255,160],
            pickable=True
        )
        view_state = pdk.ViewState(
            latitude=np.mean([p["lat"] for p in pontos]),
            longitude=np.mean([p["lon"] for p in pontos]),
            zoom=11
        )
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state))
    else:
        st.info("Nenhum ponto válido para exibir no mapa.")
else:
    st.info("Nenhum registro encontrado para a data selecionada.")

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

