import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pika
from prophet.serialize import model_from_json
from pymongo import MongoClient


# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("nova-previsao")


# ============================================================
# Variáveis de ambiente
# ============================================================

def get_env(nome):
    valor = os.getenv(nome)

    if not valor:
        logger.error(
            "A variável de ambiente %s não foi definida",
            nome
        )
        sys.exit(1)

    return valor


RABBITMQ_URL = get_env("RABBITMQ_URL")
RABBITMQ_QUEUE = get_env("RABBITMQ_QUEUE_PREVISAO")

MONGO_URL = get_env("MONGO_URL")
DB_NAME = get_env("DATABASE_NAME")
COLLECTION_NAME = get_env("COLLECTION_PREVISAO")


# ============================================================
# Diretório dos modelos
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
PASTA_MODELOS = BASE_DIR / "modelos"


logger.info("Iniciando N.O.V.A | Previsão de demanda")


# ============================================================
# Carregamento dos modelos
# ============================================================

def carregar_modelos():
    lojas = {}

    for pasta_loja in PASTA_MODELOS.iterdir():
        if not pasta_loja.is_dir():
            continue

        metadata_file = pasta_loja / "metadata.json"

        # Pastas como a de loja_02 podem existir ainda sem modelos
        if not metadata_file.exists():
            continue

        with open(
            metadata_file,
            "r",
            encoding="utf-8"
        ) as arquivo:
            metadata = json.load(arquivo)

        loja_id = metadata["loja_id"]
        arquivos_modelos = metadata["models"]

        modelos = {}

        for produto, nome_arquivo in arquivos_modelos.items():
            caminho = pasta_loja / nome_arquivo

            if not caminho.exists():
                raise FileNotFoundError(
                    f"Modelo não encontrado: {caminho}"
                )

            modelo_json = caminho.read_text(
                encoding="utf-8"
            )

            modelos[produto] = model_from_json(
                modelo_json
            )

            logger.info(
                "Modelo carregado | %s | %s",
                loja_id,
                produto
            )

        lojas[loja_id] = modelos

    if not lojas:
        raise RuntimeError(
            "Nenhuma loja com modelos foi encontrada"
        )

    return lojas


try:
    modelos_lojas = carregar_modelos()

    logger.info(
        "%d loja(s) com modelos carregados",
        len(modelos_lojas)
    )

except Exception as erro:
    logger.error(
        "Erro ao carregar modelos | %s",
        erro
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

        logger.info("Conectado ao MongoDB")
        break

    except Exception as erro:
        logger.warning(
            "MongoDB não está pronto | %s",
            erro
        )

        time.sleep(5)


# ============================================================
# Previsão
# ============================================================

def gerar_previsao(modelo, horizonte_dias):
    futuro = modelo.make_future_dataframe(
        periods=horizonte_dias,
        freq="D",
        include_history=False
    )

    previsao = modelo.predict(futuro)

    return previsao[
        [
            "ds",
            "yhat",
            "yhat_lower",
            "yhat_upper"
        ]
    ]


# ============================================================
# Processamento das mensagens
# ============================================================

def processar_msg(canal, metodo, propriedades, corpo):
    try:
        mensagem = json.loads(corpo)

        loja_id = mensagem.get("loja_id")

        if not loja_id:
            raise ValueError(
                "loja_id não informado"
            )

        if loja_id not in modelos_lojas:
            raise ValueError(
                f"Loja sem modelos disponíveis: {loja_id}"
            )

        horizonte_dias = int(
            mensagem.get("horizonte_dias", 365)
        )

        if horizonte_dias < 1 or horizonte_dias > 365:
            raise ValueError(
                "horizonte_dias deve estar entre 1 e 365"
            )

        modelos_loja = modelos_lojas[loja_id]

        produtos = mensagem.get("produtos")

        # Se nenhum produto for informado,
        # prevê todos os produtos disponíveis da loja
        if produtos is None:
            produtos = list(
                modelos_loja.keys()
            )

        if isinstance(produtos, str):
            produtos = [produtos]

        if not isinstance(produtos, list):
            raise ValueError(
                "produtos deve ser uma lista"
            )

        batch_id = str(uuid4())

        data_geracao = datetime.now(
            timezone.utc
        )

        documentos = []

        logger.info(
            "Previsão solicitada | loja=%s | produtos=%d | horizonte=%d",
            loja_id,
            len(produtos),
            horizonte_dias
        )

        for produto in produtos:
            if produto not in modelos_loja:
                logger.warning(
                    "Produto sem modelo | %s | %s",
                    loja_id,
                    produto
                )
                continue

            modelo = modelos_loja[produto]

            forecast = gerar_previsao(
                modelo,
                horizonte_dias
            )

            for _, linha in forecast.iterrows():
                quantidade = max(
                    0,
                    float(linha["yhat"])
                )

                limite_inferior = max(
                    0,
                    float(linha["yhat_lower"])
                )

                limite_superior = max(
                    0,
                    float(linha["yhat_upper"])
                )

                documento = {
                    "batch_id": batch_id,
                    "loja_id": loja_id,
                    "produto_nome": produto,

                    "data_previsao": linha[
                        "ds"
                    ].to_pydatetime(),

                    "quantidade_prevista": round(
                        quantidade,
                        2
                    ),

                    "limite_inferior": round(
                        limite_inferior,
                        2
                    ),

                    "limite_superior": round(
                        limite_superior,
                        2
                    ),

                    "data_geracao": data_geracao
                }

                documentos.append(
                    documento
                )

            logger.info(
                "Previsão gerada | %s | %d dias",
                produto,
                len(forecast)
            )

        if not documentos:
            raise ValueError(
                "Nenhuma previsão foi gerada"
            )

        collection.insert_many(
            documentos
        )

        logger.info(
            "%d previsão(ões) salvas | batch=%s",
            len(documentos),
            batch_id
        )

        canal.basic_ack(
            delivery_tag=metodo.delivery_tag
        )

    except Exception as erro:
        logger.error(
            "Erro ao processar mensagem | %s",
            erro
        )

        canal.basic_nack(
            delivery_tag=metodo.delivery_tag,
            requeue=False
        )


# ============================================================
# RabbitMQ
# ============================================================

logger.info(
    "Conectando ao RabbitMQ"
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

        logger.info(
            "Consumindo fila %s",
            RABBITMQ_QUEUE
        )

        canal.start_consuming()

    except pika.exceptions.AMQPConnectionError:
        logger.warning(
            "RabbitMQ não está pronto. Tentando novamente..."
        )

        time.sleep(5)

    except KeyboardInterrupt:
        logger.info(
            "N.O.V.A encerrada"
        )

        break