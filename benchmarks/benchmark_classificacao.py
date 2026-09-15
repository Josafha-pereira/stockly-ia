import json
import os
import random
import subprocess
import threading
import time
from uuid import uuid4

import pika
from pymongo import MongoClient
import re

RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL",
    "amqp://nova:nova_password@localhost:5672/%2F"
)

QUEUE_NAME = os.getenv(
    "RABBITMQ_QUEUE_CLASSIFICACAO",
    "fila_frutas_nova"
)

MONGO_URL = os.getenv(
    "MONGO_URL",
    "mongodb://admin:password@localhost:27017/gestao_projeto?authSource=admin"
)

DB_NAME = os.getenv(
    "DATABASE_NAME",
    "gestao_projeto"
)

COLLECTION_NAME = os.getenv(
    "COLLECTION_CLASSIFICACAO",
    "classificacoes_frutas"
)

CONTAINER = "nova_classificacao"

ITENS_POR_RODADA = 1000
RODADAS = 10

FRUTAS = [
    "banana",
    "laranja",
    "abacaxi",
    "tomate"
]


def memoria_para_mb(valor):
    correspondencia = re.fullmatch(
        r"([\d.]+)\s*([a-zA-Z]+)",
        valor.strip()
    )

    if not correspondencia:
        raise ValueError(
            f"Formato de memória não reconhecido: {valor}"
        )

    numero = float(
        correspondencia.group(1)
    )

    unidade = (
        correspondencia.group(2)
        .lower()
    )

    fatores = {
        "b": 1 / 1_000_000,
        "kb": 1 / 1000,
        "kib": 1024 / 1_000_000,
        "mb": 1,
        "mib": 1.048576,
        "gb": 1000,
        "gib": 1073.741824
    }

    if unidade not in fatores:
        raise ValueError(
            f"Unidade de memória não reconhecida: {unidade}"
        )

    return numero * fatores[unidade]


def monitorar_container(parar, resultados):
    while not parar.is_set():
        processo = subprocess.run(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{.CPUPerc}}|{{.MemUsage}}",
                CONTAINER
            ],
            capture_output=True,
            text=True
        )

        if processo.returncode != 0:
            time.sleep(0.2)
            continue

        linha = processo.stdout.strip()

        if not linha:
            time.sleep(0.2)
            continue

        try:
            cpu_texto, memoria_texto = linha.split("|", 1)

            cpu = float(
                cpu_texto
                .replace("%", "")
                .replace(",", ".")
                .strip()
            )

            memoria_atual = (
                memoria_texto
                .split("/")[0]
                .strip()
            )

            ram_mb = memoria_para_mb(
                memoria_atual
            )

            resultados.append(
                {
                    "cpu": cpu,
                    "ram_mb": ram_mb
                }
            )

        except (ValueError, IndexError):
            pass

        time.sleep(0.2)


def medir_ocioso(segundos=5):
    resultados = []
    parar = threading.Event()

    thread = threading.Thread(
        target=monitorar_container,
        args=(parar, resultados)
    )

    thread.start()
    time.sleep(segundos)
    parar.set()
    thread.join()

    return resultados


def gerar_leituras():
    leituras = []

    for _ in range(ITENS_POR_RODADA):
        leituras.append(
            {
                "fruta": random.choice(FRUTAS),
                "temperatura": round(
                    random.uniform(21, 27),
                    2
                ),
                "umidade": round(
                    random.uniform(71, 95),
                    2
                ),
                "co2": round(
                    random.uniform(20, 478),
                    2
                )
            }
        )

    return leituras


cliente_mongo = MongoClient(
    MONGO_URL,
    serverSelectionTimeoutMS=5000
)

cliente_mongo.admin.command("ping")

collection = cliente_mongo[
    DB_NAME
][COLLECTION_NAME]


print("Medindo estado ocioso...")

stats_ocioso = medir_ocioso()


benchmark_id = (
    f"benchmark_{uuid4().hex[:8]}"
)

parametros = pika.URLParameters(
    RABBITMQ_URL
)

conexao = pika.BlockingConnection(
    parametros
)

canal = conexao.channel()

canal.queue_declare(
    queue=QUEUE_NAME,
    durable=True
)


print("Iniciando carga...")

stats_carga = []
parar_monitoramento = threading.Event()

thread_monitor = threading.Thread(
    target=monitorar_container,
    args=(
        parar_monitoramento,
        stats_carga
    )
)

thread_monitor.start()

inicio = time.perf_counter()

for _ in range(RODADAS):
    payload = {
        "loja_id": benchmark_id,
        "dados": gerar_leituras()
    }

    canal.basic_publish(
        exchange="",
        routing_key=QUEUE_NAME,
        body=json.dumps(payload),
        properties=pika.BasicProperties(
            delivery_mode=2
        )
    )

conexao.close()


total_esperado = (
    ITENS_POR_RODADA * RODADAS
)

while True:
    processados = collection.count_documents(
        {
            "loja_id": benchmark_id
        }
    )

    if processados >= total_esperado:
        break

    time.sleep(0.1)


tempo_total = (
    time.perf_counter() - inicio
)

parar_monitoramento.set()
thread_monitor.join()

if not stats_ocioso:
    raise RuntimeError(
        f"Não foi possível coletar métricas ociosas do container {CONTAINER}."
    )

if not stats_carga:
    raise RuntimeError(
        f"Não foi possível coletar métricas em carga do container {CONTAINER}."
    )
    
cpu_ocioso = (
    sum(x["cpu"] for x in stats_ocioso)
    / len(stats_ocioso)
)

ram_ociosa = (
    sum(x["ram_mb"] for x in stats_ocioso)
    / len(stats_ocioso)
)

cpu_pico = max(
    x["cpu"]
    for x in stats_carga
)

ram_pico = max(
    x["ram_mb"]
    for x in stats_carga
)

throughput = (
    total_esperado / tempo_total
)


print("\nBENCHMARK DE CLASSIFICAÇÃO")
print("=" * 45)

print(
    f"Itens processados: {total_esperado}"
)

print(
    f"Tempo total: {tempo_total:.2f} s"
)

print(
    f"Throughput: {throughput:.2f} itens/s"
)

print(
    f"CPU ociosa média: {cpu_ocioso:.2f}%"
)

print(
    f"CPU em carga - pico: {cpu_pico:.2f}%"
)

print(
    f"RAM ociosa média: {ram_ociosa:.2f} MB"
)

print(
    f"RAM em carga - pico: {ram_pico:.2f} MB"
)


collection.delete_many(
    {
        "loja_id": benchmark_id
    }
)

cliente_mongo.close()

print(
    "\nDocumentos do benchmark removidos do MongoDB."
)