import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
import re
import pika
from pymongo import MongoClient


RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL",
    "amqp://nova:nova_password@localhost:5672/%2F"
)

QUEUE_NAME = os.getenv(
    "RABBITMQ_QUEUE_PREVISAO",
    "fila_previsao_demanda"
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
    "COLLECTION_PREVISAO",
    "previsoes_demanda"
)

CONTAINER = "nova_previsao"

LOJA_ID = "loja_demo"
HORIZONTE_DIAS = 365
RODADAS = 5


BASE_DIR = Path(__file__).resolve().parents[1]

METADATA = (
    BASE_DIR
    / "modelo_previsao"
    / "modelos"
    / LOJA_ID
    / "metadata.json"
)


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


with open(
    METADATA,
    "r",
    encoding="utf-8"
) as arquivo:
    metadata = json.load(arquivo)

quantidade_modelos = len(
    metadata["models"]
)

previsoes_por_rodada = (
    quantidade_modelos
    * HORIZONTE_DIAS
)

total_esperado = (
    previsoes_por_rodada
    * RODADAS
)


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


inicio_benchmark = datetime.now(
    timezone.utc
)

quantidade_inicial = (
    collection.count_documents(
        {
            "loja_id": LOJA_ID
        }
    )
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
    mensagem = {
        "loja_id": LOJA_ID,
        "horizonte_dias": HORIZONTE_DIAS
    }

    canal.basic_publish(
        exchange="",
        routing_key=QUEUE_NAME,
        body=json.dumps(mensagem),
        properties=pika.BasicProperties(
            delivery_mode=2
        )
    )

conexao.close()


while True:
    quantidade_atual = (
        collection.count_documents(
            {
                "loja_id": LOJA_ID
            }
        )
    )

    novos_documentos = (
        quantidade_atual
        - quantidade_inicial
    )

    if novos_documentos >= total_esperado:
        break

    time.sleep(0.2)


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
    total_esperado
    / tempo_total
)


print("\nBENCHMARK DE PREVISÃO")
print("=" * 45)

print(
    f"Modelos por rodada: {quantidade_modelos}"
)

print(
    f"Horizonte: {HORIZONTE_DIAS} dias"
)

print(
    f"Rodadas: {RODADAS}"
)

print(
    f"Previsões geradas: {total_esperado}"
)

print(
    f"Tempo total: {tempo_total:.2f} s"
)

print(
    f"Throughput: {throughput:.2f} previsões/s"
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
        "loja_id": LOJA_ID,
        "data_geracao": {
            "$gte": inicio_benchmark
        }
    }
)

cliente_mongo.close()

print(
    "\nDocumentos do benchmark removidos do MongoDB."
)