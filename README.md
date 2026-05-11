# Size Manager (Volume Watchdog)

API para coletar uso de disco de instalacoes Docker e guardar historico no Postgres.

O sistema encontra instalacoes com pasta `volumes/`, mede tamanho por volume, calcula distribuicao por tipo de arquivo e expoe tudo via FastAPI.

Documentacao detalhada da API: [API_REFERENCE.md](API_REFERENCE.md).

## Principais funcionalidades

- Descoberta automatica de instalacoes a partir de `ROOT_PATHS`.
- Controle de profundidade de busca com `SCAN_DEPTH`.
- Coleta de tamanho real dos volumes com `du -sb`.
- Classificacao de arquivos por categoria: fotos, videos, audios, textos e outros.
- Extracao opcional de `BACKEND_URL` no `docker-compose.yml` da instalacao.
- Historico de execucoes (`scan_runs`) e dados agregados para consulta rapida.

## Como a coleta funciona

1. Para cada raiz em `ROOT_PATHS`, o coletor percorre diretorios ate `SCAN_DEPTH`.
2. Uma instalacao e considerada valida quando contem uma pasta `volumes/`.
3. O tamanho de cada item em `volumes/*` e salvo em `volume_usage`.
4. Todos os arquivos da instalacao sao lidos para montar o total por tipo em `installation_filetype_usage`.
5. Cada execucao gera um `run_id` novo e timestamp em `scan_runs`.

## Requisitos

- Linux com utilitario `du`
- Python 3.11+
- Postgres 14+ (ou via Docker Compose)

## Estrutura do projeto

```text
app/
  main.py         # rotas da API
  collector.py    # descoberta e coleta
  database.py     # conexao e schema SQL
  config.py       # leitura de .env
  schemas.py      # modelos de resposta
scripts/
  run_api.py
  run_collection.py
```

## Configuracao

1. Copie o arquivo de ambiente:

```bash
cp .env.example .env
```

2. Ajuste as variaveis:

| Variavel | Obrigatoria | Padrao | Descricao |
| --- | --- | --- | --- |
| `DATABASE_URL` | Sim | - | String de conexao com Postgres |
| `ROOT_PATHS` | Nao | `/data/apps,/opt/stacks` | Raizes separadas por virgula |
| `SCAN_DEPTH` | Nao | `1` | Profundidade maxima da busca (minimo efetivo `0`) |
| `CORS_ALLOW_ORIGINS` | Nao | `*` | Lista CSV de origens ou `*` |
| `APP_PORT` | Nao | `8004` | Porta da API |
| `COLLECT_INTERVAL_MINUTES` | Nao | `30` | Intervalo do coletor automatico em minutos (0 desabilita) |

Exemplo (rodando via docker compose, com o host do Postgres apontando para o servico interno):

```env
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/size_manager
ROOT_PATHS=/data/apps,/opt/stacks
SCAN_DEPTH=1
CORS_ALLOW_ORIGINS=http://localhost:5173,https://frontend.exemplo.com
APP_PORT=8004
COLLECT_INTERVAL_MINUTES=30
```

> Rodando fora do docker compose? Troque `postgres` por `localhost` no `DATABASE_URL`.

## Rodando localmente

1. (Opcional) subir Postgres local:

```bash
docker compose up -d postgres
```

2. Criar ambiente Python e instalar dependencias:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Iniciar API:

```bash
python3 -m scripts.run_api
```

A API sobe na porta definida por `APP_PORT` (padrao: `8004`).

## Uso rapido

```bash
PORT="${APP_PORT:-8004}"
curl -s "http://localhost:${PORT}/health"
curl -s -X POST "http://localhost:${PORT}/collect"
curl -s "http://localhost:${PORT}/usage/latest/summary"
```

> `scanned_items` no `POST /collect` representa a quantidade de volumes coletados no run.

## Coleta manual sem API

```bash
python3 -m scripts.run_collection
```

## Endpoints principais

- `GET /health`
- `POST /collect`
- `GET /runs?limit=20`
- `GET /usage/latest`
- `GET /usage/latest/summary`
- `GET /usage/latest/file-types`
- `GET /usage/latest/file-types/by-url?url=https://instancia.exemplo.com`

UIs e contrato OpenAPI:

- Swagger UI: `/docs`
- OpenAPI JSON: `/openapi.json`

## Coleta automatica

A API inicia um scheduler (APScheduler) que executa o coletor a cada `COLLECT_INTERVAL_MINUTES` minutos. A primeira execucao acontece logo apos o startup. Para desabilitar, defina `COLLECT_INTERVAL_MINUTES=0`.

Coleta manual continua disponivel:

```bash
docker compose exec api python -m scripts.run_collection
```

## Deploy com GitHub Actions

Workflow: [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)

- `validate`: instala dependencias e roda `python -m compileall app scripts`.
- `deploy`: faz SSH no servidor, sincroniza o repositorio, grava o `.env` a partir do secret `ENV_FILE` e sobe a stack com `docker compose up -d --build`.

Pre-requisitos no servidor:

- Docker Engine + plugin `docker compose` (v2).
- Usuario SSH no grupo `docker` (ou com sudo configurado para `docker`).
- Diretorios `/data/apps` e `/opt/stacks` acessiveis ao usuario do container (montados read-only).

Secrets esperados em **Settings > Secrets and variables > Actions**:

| Secret | Descricao |
| --- | --- |
| `SSH_HOST` | Host do servidor |
| `SSH_PORT` | Porta SSH (normalmente `22`) |
| `SSH_USER` | Usuario SSH |
| `SSH_PRIVATE_KEY` | Chave privada SSH (em texto) |
| `DEPLOY_PATH` | Caminho absoluto onde o repositorio sera clonado no servidor |
| `ENV_FILE` | Conteudo completo do `.env` (DATABASE_URL com host `postgres`, ROOT_PATHS, etc.) |

Cada deploy executa `git reset --hard origin/main` em `DEPLOY_PATH`, reescreve `.env` a partir do secret e roda `docker compose up -d --build`. Os dados do Postgres persistem no volume nomeado `pgdata`.
