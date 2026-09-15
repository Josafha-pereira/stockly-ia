import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pika
from pymongo import MongoClient
from xgboost import XGBClassifier


def get_env(nome):
    valor = os.getenv(nome)

    if not valor:
        print(
            f"Erro: a variável {nome} não foi definida",
            flush=True
        )
        sys.exit(1)

    return valor


RABBITMQ_URL = get_env("RABBITMQ_URL")
RABBITMQ_QUEUE = get_env("RABBITMQ_QUEUE_CLASSIFICACAO")

MONGO_URL = get_env("MONGO_URL")
DB_NAME = get_env("DATABASE_NAME")
COLLECTION_NAME = get_env("COLLECTION_CLASSIFICACAO")


BASE_DIR = Path(__file__).resolve().parent
PASTA_MODELOS = BASE_DIR / "modelos"
METADATA_FILE = PASTA_MODELOS / "metadata.json"


print("Iniciando N.O.V.A | Classificação", flush=True)


# ============================================================
# Carregamento dos modelos
# ============================================================

try:
    with open(
        METADATA_FILE,
        "r",
        encoding="utf-8"
    ) as arquivo:
        metadata = json.load(arquivo)

    features = metadata["features"]
    mapa_alvo = metadata["target"]
    arquivos_modelos = metadata["models"]

    modelos = {}

    for fruta, nome_arquivo in arquivos_modelos.items():
        caminho = PASTA_MODELOS / nome_arquivo

        modelo = XGBClassifier()
        modelo.load_model(str(caminho))

        modelos[fruta] = modelo

        print(
            f"Modelo carregado: {fruta}",
            flush=True
        )

    rotulos = {
        valor: classe
        for classe, valor in mapa_alvo.items()
    }

except Exception as erro:
    print(
        f"Erro ao carregar os modelos: {erro}",
        flush=True
    )
    sys.exit(1)


# ============================================================
# MongoDB
# ============================================================

while True:
    try:
        mongo_cliente = MongoClient(
            MONGO_URL,
            serverSelectionTimeoutMS=5000
        )

        mongo_cliente.admin.command("ping")

        banco = mongo_cliente[DB_NAME]
        collection = banco[COLLECTION_NAME]

        print(
            "Conectado ao MongoDB",
            flush=True
        )

        break

    except Exception as erro:
        print(
            f"MongoDB não está pronto: {erro}",
            flush=True
        )

        time.sleep(5)


# ============================================================
# Frutas aceitas
# ============================================================

mapa_frutas = {
    "banana": ("Banana", "banana"),

    "orange": ("Orange", "laranja"),
    "laranja": ("Orange", "laranja"),

    "pineapple": ("Pineapple", "abacaxi"),
    "abacaxi": ("Pineapple", "abacaxi"),

    "tomato": ("Tomato", "tomate"),
    "tomate": ("Tomato", "tomate")
}


# ============================================================
# Predição
# ============================================================

def prever(leitura):
    fruta_recebida = str(
        leitura.get("fruta", "")
    ).lower().strip()

    if fruta_recebida not in mapa_frutas:
        raise ValueError(
            f"Fruta não suportada: {fruta_recebida}"
        )

    fruta_modelo, fruta_saida = mapa_frutas[
        fruta_recebida
    ]

    temperatura = leitura.get("temperatura")
    umidade = leitura.get("umidade")
    co2 = leitura.get("co2")

    if temperatura is None:
        raise ValueError(
            "Temperatura não informada"
        )

    if umidade is None:
        raise ValueError(
            "Umidade não informada"
        )

    if co2 is None:
        raise ValueError(
            "CO2 não informado"
        )

    valores = {
        "Temp": float(temperatura),
        "Humid (%)": float(umidade),
        "CO2 (pmm)": float(co2)
    }

    entrada = pd.DataFrame(
        [
            [
                valores[feature]
                for feature in features
            ]
        ],
        columns=features
    )

    modelo = modelos[fruta_modelo]

    probabilidade_ruim = float(
        modelo.predict_proba(entrada)[0][1]
    )

    classe_id = (
        1
        if probabilidade_ruim >= 0.5
        else 0
    )

    classe_original = rotulos[
        classe_id
    ]

    resultado = {
        "Good": "bom",
        "Bad": "ruim"
    }[classe_original]

    return {
        "fruta": fruta_saida,
        "fruta_modelo": fruta_modelo,
        "temperatura": float(temperatura),
        "umidade": float(umidade),
        "co2": float(co2),
        "classe_modelo": classe_original,
        "resultado": resultado,
        "probabilidade_ruim": probabilidade_ruim
    }


# ============================================================
# Processamento das mensagens
# ============================================================

def processar_msg(
    canal,
    metodo,
    propriedades,
    corpo
):
    try:
        mensagem = json.loads(corpo)

        loja_id = mensagem.get("loja_id")

        if not loja_id:
            raise ValueError(
                "loja_id não informado"
            )

        leituras = mensagem.get(
            "dados",
            []
        )

        if not leituras:
            print(
                "Mensagem recebida sem dados",
                flush=True
            )

            canal.basic_ack(
                delivery_tag=metodo.delivery_tag
            )

            return

        resultados = []

        for leitura in leituras:
            resultado = prever(
                leitura
            )

            documento = {
                "loja_id": loja_id,
                **resultado,
                "data_analise": datetime.now(
                    timezone.utc
                )
            }

            resultados.append(
                documento
            )

            print(
                f"Predição | loja={loja_id} | "
                f"{resultado['fruta']} -> "
                f"{resultado['resultado']} | "
                f"P(ruim)="
                f"{resultado['probabilidade_ruim']:.4f}",
                flush=True
            )

        collection.insert_many(
            resultados
        )

        print(
            f"Salvo no MongoDB: "
            f"{len(resultados)} resultado(s)",
            flush=True
        )

        canal.basic_ack(
            delivery_tag=metodo.delivery_tag
        )

    except Exception as erro:
        print(
            f"Erro ao processar mensagem: {erro}",
            flush=True
        )

        canal.basic_nack(
            delivery_tag=metodo.delivery_tag,
            requeue=False
        )


# ============================================================
# RabbitMQ
# ============================================================

print(
    "Conectando ao RabbitMQ",
    flush=True
)

while True:
    try:
        parametros = pika.URLParameters(
            RABBITMQ_URL
        )

        conexao = pika.BlockingConnection(
            parametros
        )

        canal = conexao.channel()

        canal.queue_declare(
            queue=RABBITMQ_QUEUE,
            durable=True
        )

        canal.basic_qos(
            prefetch_count=1
        )

        canal.basic_consume(
            queue=RABBITMQ_QUEUE,
            on_message_callback=processar_msg,
            auto_ack=False
        )

        print(
            f"Consumindo fila: {RABBITMQ_QUEUE}",
            flush=True
        )

        canal.start_consuming()

    except pika.exceptions.AMQPConnectionError:
        print(
            "RabbitMQ não está pronto. "
            "Tentando novamente...",
            flush=True
        )

        time.sleep(5)

    except KeyboardInterrupt:
        print(
            "N.O.V.A encerrada",
            flush=True
        )

        break