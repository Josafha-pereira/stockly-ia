import json
import os

import pika


RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL",
    "amqp://nova:nova_password@localhost:5672/%2F"
)

QUEUE_NAME = os.getenv(
    "RABBITMQ_QUEUE_PREVISAO",
    "fila_previsao_demanda"
)


mensagem = {
    "loja_id": "loja_demo",
    "produtos": [
        "Arroz Agulhinha Tipo 1 Camil 5kg",
        "Café Pilão Tradicional 500g"
    ],
    "horizonte_dias": 30
}


try:
    print("Conectando ao RabbitMQ")

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

    canal.basic_publish(
        exchange="",
        routing_key=QUEUE_NAME,
        body=json.dumps(
            mensagem,
            ensure_ascii=False
        ),
        properties=pika.BasicProperties(
            delivery_mode=2
        )
    )

    print("Mensagem de previsão enviada")
    print(
        json.dumps(
            mensagem,
            indent=2,
            ensure_ascii=False
        )
    )

    conexao.close()

except Exception as erro:
    print(
        f"Erro ao enviar mensagem: {erro}"
    )