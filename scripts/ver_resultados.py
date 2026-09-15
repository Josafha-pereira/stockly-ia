import json
import os
from datetime import datetime

from pymongo import MongoClient


MONGO_URL = os.getenv(
    "MONGO_URL",
    "mongodb://admin:password@localhost:27017/gestao_projeto?authSource=admin"
)

DB_NAME = os.getenv(
    "DATABASE_NAME",
    "gestao_projeto"
)

COLLECTION_CLASSIFICACAO = os.getenv(
    "COLLECTION_CLASSIFICACAO",
    "classificacoes_frutas"
)

COLLECTION_PREVISAO = os.getenv(
    "COLLECTION_PREVISAO",
    "previsoes_demanda"
)


def serializar_json(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()

    return str(obj)


def mostrar_documento(documento):
    print(
        json.dumps(
            documento,
            indent=2,
            ensure_ascii=False,
            default=serializar_json
        )
    )


try:
    cliente = MongoClient(
        MONGO_URL,
        serverSelectionTimeoutMS=5000
    )

    cliente.admin.command("ping")

    banco = cliente[DB_NAME]

    print("\nConectado ao MongoDB")


    # ========================================================
    # Classificação
    # ========================================================

    classificacoes = banco[
        COLLECTION_CLASSIFICACAO
    ]

    total_classificacoes = (
        classificacoes.count_documents({})
    )

    lojas_classificacao = (
        classificacoes.distinct("loja_id")
    )

    print("\n========================================")
    print("CLASSIFICAÇÕES DE FRUTAS")
    print("========================================")

    print(
        f"Total de documentos: "
        f"{total_classificacoes}"
    )

    print(
        f"Lojas encontradas: "
        f"{lojas_classificacao}"
    )

    for loja_id in lojas_classificacao:
        documento = classificacoes.find_one(
            {
                "loja_id": loja_id
            },
            {
                "_id": 0
            },
            sort=[
                ("data_analise", -1)
            ]
        )

        if documento:
            print(
                f"\nÚltima classificação "
                f"da loja {loja_id}"
            )

            mostrar_documento(
                documento
            )


    # ========================================================
    # Previsão
    # ========================================================

    previsoes = banco[
        COLLECTION_PREVISAO
    ]

    total_previsoes = (
        previsoes.count_documents({})
    )

    lojas_previsao = (
        previsoes.distinct("loja_id")
    )

    print("\n========================================")
    print("PREVISÕES DE DEMANDA")
    print("========================================")

    print(
        f"Total de documentos: "
        f"{total_previsoes}"
    )

    print(
        f"Lojas encontradas: "
        f"{lojas_previsao}"
    )

    for loja_id in lojas_previsao:
        documento = previsoes.find_one(
            {
                "loja_id": loja_id
            },
            {
                "_id": 0
            },
            sort=[
                ("data_geracao", -1)
            ]
        )

        if documento:
            print(
                f"\nAmostra de previsão "
                f"da loja {loja_id}"
            )

            mostrar_documento(
                documento
            )


except Exception as erro:
    print(
        f"\nErro ao acessar MongoDB\n{erro}"
    )