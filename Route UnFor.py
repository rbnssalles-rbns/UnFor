#!/usr/bin/env python
# coding: utf-8

# In[4]:


import streamlit as st
import pandas as pd
import requests
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

st.title("🚚 Otimizador de Rotas - Fortaleza e Região")

RAPIDAPI_KEY = "0db87cfda8mshbed9238b8a36debp1e12eajsnaa71e8ddd25a"

# Função de geocodificação com fallback automático
def forward_geocode(endereco):
    tentativas = [
        endereco.strip(),
        " ".join(endereco.split(",")[:2]).strip(),  # rua + número
        endereco.split(",")[0].strip(),            # só rua/avenida
    ]
    for tentativa in tentativas:
        url = "https://trueway-geocoding-api-forward-and-reverse-geocoding.p.rapidapi.com/GeocodingService"
        querystring = {"address": tentativa, "language": "pt"}
        headers = {
            "x-rapidapi-host": "trueway-geocoding-api-forward-and-reverse-geocoding.p.rapidapi.com",
            "x-rapidapi-key": RAPIDAPI_KEY
        }
        response = requests.get(url, headers=headers, params=querystring)
        data = response.json()
        if "results" in data and len(data["results"]) > 0:
            loc = data["results"][0]["location"]
            return (loc["lat"], loc["lng"])
    return None

# Função para criar matriz de distâncias
def create_distance_matrix(locations):
    coords = ["{},{}".format(lat, lon) for lat, lon in locations]
    origins = ";".join(coords)
    destinations = ";".join(coords)

    url = "https://trueway-matrix.p.rapidapi.com/CalculateDrivingMatrix"
    querystring = {"origins": origins, "destinations": destinations}
    headers = {
        "x-rapidapi-host": "trueway-matrix.p.rapidapi.com",
        "x-rapidapi-key": RAPIDAPI_KEY
    }
    response = requests.get(url, headers=headers, params=querystring)
    data = response.json()
    if "distances" not in data:
        st.error(f"❌ Erro na resposta da API: {data}")
        st.stop()
    matrix = data["distances"]
    return [[dist/1000 for dist in row] for row in matrix]  # km

# Input de veículos e placas
num_veiculos = st.number_input("Quantos veículos vão atender?", min_value=1, max_value=10, value=3)
placas = []
for i in range(num_veiculos):
    placa = st.text_input(f"Digite a placa do veículo {i+1}")
    placas.append(placa)

# Campo para origem de partida
endereco_origem = st.text_input("📍 Informe o endereço de origem (ponto de partida)")

# Upload do arquivo Excel
uploaded_file = st.file_uploader("📂 Envie o arquivo Excel (.xlsx) com endereços", type=["xlsx"])

if uploaded_file and all(placas) and endereco_origem:
    df = pd.read_excel(uploaded_file)
    st.write("Endereços carregados:")
    st.dataframe(df)

    # Validador da origem com fallback
    origem_coords = forward_geocode(endereco_origem)
    if not origem_coords:
        st.error("❌ Não foi possível localizar o endereço de origem, mesmo após tentativas simplificadas.")
        st.stop()

    # Geocodificação dos endereços do Excel
    df["Coordenadas"] = df["Endereço"].apply(forward_geocode)
    df["Latitude"] = df["Coordenadas"].apply(lambda x: x[0] if x else None)
    df["Longitude"] = df["Coordenadas"].apply(lambda x: x[1] if x else None)

    # Mostrar endereços inválidos
    enderecos_invalidos = df[df["Latitude"].isna()]["Endereço"].tolist()
    if enderecos_invalidos:
        st.warning(f"⚠️ Os seguintes endereços não foram reconhecidos: {enderecos_invalidos}")

    # Inserir origem no início da lista de locais
    df_validos = df.dropna(subset=["Latitude", "Longitude"])
    locations = [origem_coords] + list(zip(df_validos["Latitude"], df_validos["Longitude"]))

    # Criar matriz de distâncias
    distance_matrix = create_distance_matrix(locations)

    # Configuração do solver
    manager = pywrapcp.RoutingIndexManager(len(distance_matrix), num_veiculos, [0]*num_veiculos)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(distance_matrix[from_node][to_node] * 1000)

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Restrição de capacidade
    demanda_por_ponto = [1] * len(distance_matrix)
    capacidade_veiculos = [10] * num_veiculos

    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return demanda_por_ponto[from_node]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,
        capacidade_veiculos,
        True,
        "Capacity"
    )

    # Restrição de distância máxima (70 km)
    routing.AddDimension(
        transit_callback_index,
        0,
        70000,
        True,
        "Distance"
    )

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC

    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        resultados = []
        for veiculo_id in range(num_veiculos):
            index = routing.Start(veiculo_id)
            rota = []
            distancia_acumulada = 0

            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                proximo_index = solution.Value(routing.NextVar(index))
                proximo_node = manager.IndexToNode(proximo_index)

                if not routing.IsEnd(proximo_index):
                    dist = distance_matrix[node_index][proximo_node]
                else:
                    dist = 0

                distancia_acumulada += dist

                resultados.append({
                    "Placa": placas[veiculo_id],
                    "Ordem": len(rota)+1,
                    "Endereço": df_validos.iloc[node_index-1]["Endereço"] if node_index > 0 else endereco_origem,
                    "Latitude": locations[node_index][0],
                    "Longitude": locations[node_index][1],
                    "Distância até próximo (km)": round(dist, 2),
                    "Distância acumulada (km)": round(distancia_acumulada, 2)
                })

                rota.append(node_index)
                index = proximo_index

        df_resultados = pd.DataFrame(resultados)
        st.success("✅ Rotas otimizadas calculadas com fallback automático na origem")
        st.dataframe(df_resultados)
        st.map(df_resultados[["Latitude", "Longitude"]])


# In[ ]:




