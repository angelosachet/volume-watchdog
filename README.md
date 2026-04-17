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

Exemplo:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/size_manager
ROOT_PATHS=/data/apps,/opt/stacks
SCAN_DEPTH=1
CORS_ALLOW_ORIGINS=http://localhost:5173,https://frontend.exemplo.com
APP_PORT=8004
```

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

## Agendamento com cron

Exemplo (a cada 30 minutos):

```bash
*/30 * * * * cd /home/angelo/projects/size-manager && /home/angelo/projects/size-manager/.venv/bin/python3 -m scripts.run_collection >> /var/log/size-manager.log 2>&1
```

## Deploy com GitHub Actions

Workflow: [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)

- `validate`: instala dependencias e roda `python -m compileall app scripts`
- `deploy`: publica via SSH no servidor

Secrets esperados em **Settings > Secrets and variables > Actions**:

- `SSH_HOST`
- `SSH_PORT`
- `SSH_USER`
- `SSH_PRIVATE_KEY`
- `DEPLOY_PATH`
- `DEPLOY_COMMAND`

Exemplo de `DEPLOY_COMMAND` (processo Python simples):

```bash
if [ -f app.pid ] && kill -0 "$(cat app.pid)" 2>/dev/null; then
  kill "$(cat app.pid)"
  sleep 1
fi
nohup .venv/bin/python3 -m scripts.run_api > app.log 2>&1 &
echo $! > app.pid
```
