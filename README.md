# N.O.V.A

**Núcleo de Otimização de Vendas e Ambiente**

A N.O.V.A é o módulo de inteligência artificial da Stockly, um sistema acadêmico de gestão de estoque para supermercados. Este repositório reúne a pesquisa, o treinamento dos modelos e a execução local de dois microserviços de Machine Learning

- classificação das condições de armazenamento de frutas com XGBoost
- previsão de demanda com Prophet

O projeto foi desenvolvido na disciplina Projetos de Engenharia 3.

## Visão geral

| Serviço | Modelo | Entrada principal | Resultado |
| --- | --- | --- | --- |
| Classificação | XGBoost | fruta, temperatura, umidade e CO2 | classe `bom` ou `ruim` e probabilidade de `ruim` |
| Previsão | Prophet | loja, produto e horizonte | previsão diária com intervalo de incerteza de 80% |

Os notebooks concentram a análise, a validação e o treinamento. Os microserviços carregam os modelos salvos em JSON e recebem as solicitações pelo RabbitMQ.


## Arquitetura da Stockly

```mermaid
flowchart TB
    NV[NV200 e sensores] --> B[Backend Stockly]
    ERP[ERP e histórico de vendas] --> B
    B --> R[RabbitMQ]
    R --> N[N.O.V.A]
    N --> M[(MongoDB)]
    B --> F[Frontend]
```

> **Nota**  O NV200 é o módulo de sensores da Stockly. Ele faz as medições ambientais. O backend recebe essas leituras e calcula a mediana de uma janela de tempo, após isso é feita a solicitação para classificação.


## Arquitetura do repositório

Na execução local, o RabbitMQ recebe as mensagens dos scripts de teste e encaminha cada solicitação ao serviço correspondente. Os resultados são salvos no MongoDB.

```mermaid
flowchart TB
    T[Scripts de teste] --> R[RabbitMQ]
    R --> C[Classificação<br/>XGBoost por fruta]
    R --> P[Previsão<br/>Prophet por loja e produto]
    C --> M[(MongoDB)]
    P --> M
```

## Estrutura do projeto

```text
stockly-ia/
├── benchmarks/
│   ├── benchmark_classificacao.py
│   └── benchmark_previsao.py
│
├── docs/
│   └── images/
│       ├── mongodb_classificacao.png
│       └── mongodb_previsao.png
│
├── modelo_classificacao/
│   ├── modelos/
│   │   ├── metadata.json
│   │   ├── xgb_banana.json
│   │   ├── xgb_orange.json
│   │   ├── xgb_pineapple.json
│   │   └── xgb_tomato.json
│   │    
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
│
├── modelo_previsao/
│   ├── modelos/
│   │   ├── loja_02/
│   │   │   └── .gitkeep
│   │   └── loja_demo/
│   │       ├── metadata.json
│   │       ├── modelo_acucar_refinado_amoroso_caravelas_1kg.json
│   │       ├── modelo_arroz_agulhinha_tipo_1_camil_5kg.json
│   │       ├── modelo_cafe_pilao_tradicional_500g.json
│   │       └── modelo_feijao_carioca_tipo_1_kicaldo_1kg.json
│   │        
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
│
├── pesquisa_treinamento_classificacao/
│   ├── dataset/
│   │   └── dataset_frutas.csv
│   └── notebooks/
│       ├── nova_01_eda.ipynb
│       └── nova_02_modelagem.ipynb
│
├── pesquisa_treinamento_previsao/
│   ├── dataset/
│   │   └── data_prev.csv
│   └── notebook/
│       └── nova_previsao.ipynb
│
├── scripts/
│   └── ver_resultados.py
│
├── tests/
│   ├── teste_classificacao.py
│   └── teste_previsao.py
│
├── .gitignore
├── docker-compose.yml
├── env.example
├── README.md
└── requirements-notebooks.txt
```

## Organização dos modelos

### Classificação

A classificação utiliza quatro modelos XGBoost, um para cada fruta

```text
Banana
Orange
Pineapple
Tomato
```

Os mesmos modelos podem atender diferentes lojas. Cada solicitação informa `loja_id`, fruta, temperatura, umidade e CO2. O serviço escolhe o modelo da fruta, calcula a probabilidade da classe `Bad` e salva o resultado no MongoDB junto com a identificação da loja.

Antes de usar os modelos em uma loja real, é necessário validá-los com dados coletados pelos sensores e nas condições ambientais dessa loja.

### Previsão

Na previsão, os modelos são separados por loja e produto

```text
modelo_previsao/modelos/
├── loja_demo/
│   ├── modelo_arroz_agulhinha_tipo_1_camil_5kg.json
│   ├── modelo_feijao_carioca_tipo_1_kicaldo_1kg.json
│   ├── modelo_acucar_refinado_amoroso_caravelas_1kg.json
│   ├── modelo_cafe_pilao_tradicional_500g.json
│   └── metadata.json
│
└── loja_02/
    └── .gitkeep
```

A `loja_demo` contém os modelos usados na demonstração. Para uma nova loja, o histórico de vendas do ERP deve passar pelas etapas de análise, validação cruzada e treinamento antes da geração dos modelos Prophet.

Em uma integração com ERP, cada produto pode ser identificado pelo SKU ou código interno do sistema e associado ao nome exibido pela aplicação.

## Pesquisa e treinamento

### Classificação de frutas

Os notebooks estão em

```text
pesquisa_treinamento_classificacao/notebooks/nova_01_eda.ipynb
pesquisa_treinamento_classificacao/notebooks/nova_02_modelagem.ipynb
```

O dataset possui leituras de Orange, Pineapple, Banana e Tomato, com temperatura, umidade, luminosidade, CO2 e rótulo `Good` ou `Bad`. Após a remoção das cópias, utiliza-se 8.115 linhas de dados únicos.

`Light (Fux)` foi retirada da modelagem porque apresentou comportamento inadequado e estranho, com os dados separando totalmente rótulos Good e Bad em Orange e uma mudança abrupta de escala em parte dos registros de Tomato.

Os modelos finais usam três features

```text
Temp
Humid (%)
CO2 (pmm)
```
Além disso, foi feito o treinamento e a exportação de um classificador XGBoost para cada fruta. Os arquivos finais são salvos em `modelo_classificacao/modelos/`, onde são carregados pelo microserviço de classificação.

### Previsão de demanda

A pesquisa está em

```text
pesquisa_treinamento_previsao/notebook/nova_previsao.ipynb
```

O dataset usado nesta demonstração é sintético e foi tratado como os dados de ERP da `loja_demo`. Foram treinados e exportados modelos para quatro produtos

| Produto |
| --- |
| Arroz Agulhinha Tipo 1 Camil 5kg |
| Feijão Carioca Tipo 1 Kicaldo 1kg |
| Açúcar Refinado Amoroso Caravelas 1kg |
| Café Pilão Tradicional 500g |

O treinamento do Prophet utiliza sazonalidade anual, sazonalidade semanal, tendência e intervalo de incerteza de 80%.

A avaliação foi feita com validação cruzada e horizonte de 365 dias. O serviço aceita uma faixa de tempo entre 1 e 365 dias. As datas previstas começam após o último dia presente na série usada no treinamento. Os modelos finais da demonstração são salvos em `modelo_previsao/modelos/loja_demo/`, onde são carregados pelo microserviço de previsão.


## Tecnologias

| Componente | Versão ou imagem | Uso |
| --- | --- | --- |
| Python | 3.13.15 nos containers | execução dos microserviços |
| XGBoost | 3.4.1 | classificação |
| scikit-learn | 1.9.1 | dependência usada pelo XGBoost |
| Pandas | 2.2.3 | organização das entradas da classificação |
| Prophet | 1.4.0 | previsão de demanda |
| Pika | 1.3.2 | comunicação com RabbitMQ |
| PyMongo | 4.6.1 | comunicação com MongoDB |
| MongoDB | 7.0.41 | banco de dados |
| RabbitMQ | `rabbitmq:4-management` | filas de mensagens |
| Docker | Docker Engine | execução dos containers |
| Docker Compose | plugin Compose | inicialização dos serviços |

## Execução local

### Pré-requisitos

São necessários Docker, Docker Compose, Git e Python 3. Para executar os notebooks localmente pelo VS Code, também são necessárias as extensões Python e Jupyter.

Clone o repositório

```bash
git clone https://github.com/Josafha-pereira/stockly-ia.git
cd stockly-ia
```

Crie o `.env` a partir do arquivo de exemplo

```bash
cp env.example .env
```

Conteúdo usado no env.example

```env
# RabbitMQ
RABBITMQ_URL=amqp://nova:nova_password@localhost:5672/%2F
RABBITMQ_QUEUE_CLASSIFICACAO=fila_frutas_nova
RABBITMQ_QUEUE_PREVISAO=fila_previsao_demanda

# MongoDB
MONGO_URL=mongodb://admin:password@localhost:27017/gestao_projeto?authSource=admin
DATABASE_NAME=gestao_projeto
COLLECTION_CLASSIFICACAO=classificacoes_frutas
COLLECTION_PREVISAO=previsoes_demanda
```

As URLs com `localhost` são usadas pelos scripts executados no computador.

### Iniciando os serviços

Na raiz do projeto

```bash
docker compose up --build
```

Os quatro containers principais são

```text
nova_mongo
nova_rabbitmq
nova_classificacao
nova_previsao
```

Para verificar o estado

```bash
docker compose ps
```

Para executar em segundo plano

```bash
docker compose up --build -d
docker compose logs -f
```

Para encerrar

```bash
docker compose down
```

Para encerrar e também apagar os volumes de dados salvos locais do MongoDB e RabbitMQ

```bash
docker compose down -v
```

## Ambiente Python para notebooks, testes e scripts

Os microserviços executam dentro do Docker. Os notebooks de pesquisa, testes, benchmarks e o script de consulta podem ser executados no mesmo ambiente virtual local.

Crie o ambiente virtual na raiz do projeto

```bash
python3 -m venv .venv
```

Em Bash ou Zsh:

```bash
source .venv/bin/activate
```

No Fish Shell:

```fish
source .venv/bin/activate.fish
```

Atualize o `pip`

```bash
python -m pip install --upgrade pip
```

Instale as dependências usadas pelos notebooks

```bash
python -m pip install -r requirements-notebooks.txt
```

Para executar os testes, benchmarks e o script de consulta, instale também

```bash
python -m pip install pika==1.3.2 pymongo==4.6.1
```

### Executando os notebooks

Os datasets usados na pesquisa já estão incluídos no repositório. Mantenha a estrutura de pastas, pois os notebooks utilizam caminhos relativos para acessá-los.

Abra o projeto no VS Code

```bash
code .
```

Em cada notebook, selecione o interpretador da `.venv` como kernel do Jupyter e execute as células em ordem.

Para a pesquisa de classificação, execute

```text
pesquisa_treinamento_classificacao/notebooks/nova_01_eda.ipynb
pesquisa_treinamento_classificacao/notebooks/nova_02_modelagem.ipynb
```

Os dois notebooks utilizam

```text
pesquisa_treinamento_classificacao/dataset/dataset_frutas.csv
```

Ao final da modelagem, os classificadores e o `metadata.json` são exportados para

```text
modelo_classificacao/modelos/
```

Para a pesquisa de previsão, execute

```text
pesquisa_treinamento_previsao/notebook/nova_previsao.ipynb
```

O notebook utiliza

```text
pesquisa_treinamento_previsao/dataset/data_prev.csv
```

Ao final do treinamento, os modelos Prophet da loja demonstrativa são exportados para

```text
modelo_previsao/modelos/loja_demo/
```

## Testes de integração

### Classificação

Com os containers ativos

```bash
python tests/teste_classificacao.py
```

A mensagem de teste contém

```json
{
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
```

O serviço seleciona o modelo de laranja, executa a classificação e salva o resultado na coleção `classificacoes_frutas`.

### Previsão

Execute

```bash
python tests/teste_previsao.py
```

O teste solicita 30 dias para dois produtos

```json
{
  "loja_id": "loja_demo",
  "produtos": [
    "Arroz Agulhinha Tipo 1 Camil 5kg",
    "Café Pilão Tradicional 500g"
  ],
  "horizonte_dias": 30
}
```

São gerados 60 registros no MongoDB, correspondentes a 30 dias para cada produto.

Se `produtos` não for enviado, o serviço gera previsões para todos os modelos cadastrados na loja.

## Verificação dos resultados

### Terminal

```bash
python scripts/ver_resultados.py
```

O script mostra a quantidade de registros, as lojas encontradas e exemplos recentes das duas coleções.

### MongoDB Compass

Com os containers ativos, crie uma conexão no Compass e use

```text
mongodb://admin:password@localhost:27017/gestao_projeto?authSource=admin
```

Abra o banco `gestao_projeto`. As duas coleções são

```text
classificacoes_frutas
previsoes_demanda
```

Para filtrar a loja demonstrativa

```json
{
  "loja_id": "loja_demo"
}
```

### Resultado da classificação

![Resultado da classificação no MongoDB Compass](docs/images/mongodb_classificacao.png)

O registro contém a loja, fruta, valores dos sensores, classe prevista, probabilidade de `ruim` e data da análise.

### Resultado da previsão

![Resultado da previsão no MongoDB Compass](docs/images/mongodb_previsao.png)

Cada registro representa a previsão de um produto em um dia e contém a quantidade prevista, os limites do intervalo de incerteza e a identificação do lote gerado.

## RabbitMQ Management

A interface web do RabbitMQ fica disponível em

```text
http://localhost:15672
```

Credenciais da demonstração

```text
usuário  nova
senha    nova_password
```

Filas usadas pela N.O.V.A

```text
fila_frutas_nova
fila_previsao_demanda
```

## Benchmarks

Os benchmarks medem o fluxo completo de cada serviço, desde o envio da mensagem ao RabbitMQ até o resultado salvo no MongoDB.

Ambiente usado nos testes

```text
Acer Aspire 5
AMD Ryzen 7 5700U
8 GB de RAM
Fedora 43
Docker
```

### Classificação

```bash
python benchmarks/benchmark_classificacao.py
```

| Métrica | Resultado |
| --- | ---: |
| Itens processados | 10.000 |
| Tempo total | 21,40 s |
| Throughput | 467,25 classificações/s |
| CPU ociosa média | 0,03% |
| CPU em carga no pico | 1538,03% |
| RAM ociosa média | 102,16 MB |
| RAM em carga no pico | 104,82 MB |

O valor de CPU pode passar de 1000% porque o Docker Stats soma o uso dos processadores lógicos. O pico registrado representa uso de vários processadores lógicos ao mesmo tempo.
Como pode-se Observar, apesar do pico de processamento, o uso de memória ram não é alto. Sendo assim, conclui-se que não seria necessário um servidor com uma capacidade tão grande de processamento.
### Previsão

```bash
python benchmarks/benchmark_previsao.py
```

| Métrica | Resultado |
| --- | ---: |
| Modelos por rodada | 4 |
| Horizonte | 365 dias |
| Rodadas | 5 |
| Pontos previstos | 7.300 |
| Tempo total | 2,34 s |
| Throughput | 3.116,85 pontos previstos/s |
| CPU ociosa média | 0,05% |
| CPU em carga no pico | 97,73% |
| RAM ociosa média | 89,64 MB |
| RAM em carga no pico | 95,53 MB |

Nesse benchmark, representa-se a quantidade de pontos diários de previsão gerados por segundo. Aqui podemos ver que foi necessário até menos poder computacional, o que significa que, da mesma forma, não seria necessário um servidor com um poder computacional tão grande para conseguir rodar o microserviço. 


## Adição de novas lojas

Na classificação, uma nova loja pode usar os modelos XGBoost já carregados. O `loja_id` é enviado na mensagem e salvo junto com o resultado.

Na previsão, para cada loja será feito seu próprio conjunto de modelos. O processo parte do histórico de vendas do ERP, passa pela análise e validação cruzada, treinamento dos modelos e termina com o salvamento e integração ao sistema.

A estrutura segue este padrão

```text
modelo_previsao/modelos/
├── loja_demo/
├── loja_02/
└── loja_03/
```

Cada pasta deve ter um `metadata.json` com o `loja_id` e o mapeamento entre produtos e arquivos JSON. Os modelos são carregados quando o serviço inicia, então uma nova pasta de loja exige reiniciar o serviço de previsão.

```bash
docker compose restart previsao
```

## Variáveis de ambiente

| Variável | Função |
| --- | --- |
| `RABBITMQ_URL` | conexão com RabbitMQ |
| `RABBITMQ_QUEUE_CLASSIFICACAO` | fila da classificação |
| `RABBITMQ_QUEUE_PREVISAO` | fila da previsão |
| `MONGO_URL` | conexão com MongoDB |
| `DATABASE_NAME` | nome do banco |
| `COLLECTION_CLASSIFICACAO` | coleção da classificação |
| `COLLECTION_PREVISAO` | coleção da previsão |

## Limitações

Os classificadores foram avaliados no dataset usado na pesquisa. Para aplicação em uma loja real, os modelos precisam ser validados com dados coletados no ambiente e pelos sensores que serão usados nessa loja.

O dataset de previsão é sintético. Por isso, os resultados dos modelos Prophet descrevem o comportamento nessa base e não representam a precisão esperada em uma loja real. A quantidade vendida é usada como aproximação da demanda. Em dados reais, períodos de falta de estoque podem reduzir as vendas registradas mesmo quando existe demanda pelo produto.

Além disso, a previsão mantém um modelo por loja e produto. Uma operação com muitos SKUs precisa considerar o custo de treinamento, armazenamento e carregamento desses modelos.

## Referências

### Datasets

**Mendeley Data.** *A Multi-Parameter Dataset for Machine Learning Based Fruit Spoilage Prediction in an IoT-Enabled Cold Storage System.* Disponível em [https://data.mendeley.com/datasets/czz68d9fwj/1](https://data.mendeley.com/datasets/czz68d9fwj/1).

**Kaggle.** *Product Sales Data.* Disponível em [https://www.kaggle.com/datasets/ksabishek/product-sales-data](https://www.kaggle.com/datasets/ksabishek/product-sales-data).

### Modelagem

**CHEN, T.; GUESTRIN, C.** *XGBoost: A Scalable Tree Boosting System.* Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining, 2016.

**TAYLOR, S. J.; LETHAM, B.** *Forecasting at Scale.* The American Statistician, v. 72, n. 1, p. 37-45, 2018.

**Prophet.** *Forecasting at Scale.* Documentação oficial. Disponível em [https://facebook.github.io/prophet/](https://facebook.github.io/prophet/).

### Infraestrutura

**RabbitMQ.** *RabbitMQ Documentation.* Disponível em [https://www.rabbitmq.com/docs](https://www.rabbitmq.com/docs).

**MongoDB.** *MongoDB Manual.* Disponível em [https://www.mongodb.com/docs/manual/](https://www.mongodb.com/docs/manual/).

## Escopo

Esse repositório reúne os notebooks de pesquisa, os modelos treinados, os dois microserviços, a infraestrutura local com Docker, os testes de integração e os benchmarks da N.O.V.A.
