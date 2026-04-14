#!/usr/bin/env python
# coding: utf-8

# In[1]:


import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

st.title("🚚 Otimizador de Rotas - Fortaleza e Região")

# Input de veículos e placas
num_veiculos = st.number_input("Quantos veículos vão atender?", min_value=1, max_value=10, value=3)
placas = []
for i in range(num_veiculos):
    placa = st.text_input(f"Digite a placa do veículo {i+1}")
    placas.append(placa)

# Upload do arquivo Excel
uploaded_file = st.file_uploader("📂 Envie o arquivo Excel (.xlsx) com endereços", type=["xlsx"])

if uploaded_file and all(placas):
    df = pd.read_excel(uploaded_file)
    st.write("Endereços carregados:")
    st.dataframe(df)

    # Geocodificação
    geolocator = Nominatim(user_agent="route_optimizer")
    df["Coordenadas"] = df["Endereço"].apply(lambda x: geolocator.geocode(x))
    df["Latitude"] = df["Coordenadas"].apply(lambda x: x.latitude if x else None)
    df["Longitude"] = df["Coordenadas"].apply(lambda x: x.longitude if x else None)

    # Criar matriz de distâncias
    def create_distance_matrix(locations):
        size = len(locations)
        matrix = [[0]*size for _ in range(size)]
        for i in range(size):
            for j in range(size):
                if i != j:
                    matrix[i][j] = geodesic(locations[i], locations[j]).km
        return matrix

    locations = list(zip(df["Latitude"], df["Longitude"]))
    distance_matrix = create_distance_matrix(locations)

    # Configuração do solver
    manager = pywrapcp.RoutingIndexManager(len(distance_matrix), num_veiculos, range(num_veiculos))
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(distance_matrix[from_node][to_node] * 1000)

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Restrição de capacidade (exemplo: até 10 atendimentos por veículo)
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
        70000,  # 70 km em metros
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
                    "Endereço": df.iloc[node_index]["Endereço"],
                    "Latitude": df.iloc[node_index]["Latitude"],
                    "Longitude": df.iloc[node_index]["Longitude"],
                    "Distância até próximo (km)": round(dist, 2),
                    "Distância acumulada (km)": round(distancia_acumulada, 2)
                })

                rota.append(node_index)
                index = proximo_index

        # Exportar resultados
        df_resultados = pd.DataFrame(resultados)
        output_file = "rotas_detalhadas.xlsx"
        df_resultados.to_excel(output_file, index=False)

        st.success(f"✅ Rotas otimizadas exportadas para {output_file}")
        st.dataframe(df_resultados)
        st.map(df_resultados[["Latitude", "Longitude"]])


# In[ ]:




