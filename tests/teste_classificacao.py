import json
import os

import pika


RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL",
    "amqp://nova:nova_password@localhost:5672/%2F"
)

QUEUE_NAME = os.getenv(
    "RABBITMQ_QUEUE_CLASSIFICACAO",
    "fila_frutas_nova"
)


payload = {
    "loja_id": "loja_demo",
    "dados": [
        {
            "fruta": "laranja",
            "temperatura": 24.5,
            "umidade": 90.0,
            "co2": 350
        }
    ]
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
        body=json.dumps(payload),
        properties=pika.BasicProperties(
            delivery_mode=2
        )
    )

    print("Mensagem de classificação enviada")
    print(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False
        )
    )

    conexao.close()

except Exception as erro:
    print(
        f"Erro ao enviar mensagem: {erro}"
    )