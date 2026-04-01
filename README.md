# Volume Watchdog

Sistema para varrer instalacoes Docker dentro de diretorios raiz configurados, salvar uso de disco no Postgres e consultar via API.

Referência completa da API: [API_REFERENCE.md](API_REFERENCE.md).

## O que ele faz

- Procura instalacoes (pastas que tenham `volumes/`) dentro de cada raiz configurada.
- Usa `ROOT_PATHS` do `.env` para definir quais diretorios raiz devem ser varridos.
- Usa `SCAN_DEPTH` do `.env` para controlar ate quantos niveis abaixo de cada raiz a busca vai.
- Executa `du -sb <instalacao>/volumes/*` para obter tamanho real em bytes.
- Faz varredura de arquivos por extensao em cada instalacao (fotos/videos/audios/textos/outros), no estilo do comando `find ... | awk`.
- Le `docker-compose.yml` de cada instalacao e extrai `BACKEND_URL` quando presente.
- Salva cada leitura no Postgres com historico de coletas.
- Exibe endpoints para listar execucoes e resumo em GB.

## Requisitos

- Linux com `du`
- Python 3.11+
- Postgres 14+

## Configuracao

1. Copie o arquivo de exemplo:

```bash
cp .env.example .env
```

2. Ajuste variaveis no `.env`:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/size_manager
ROOT_PATHS=/data/apps,/opt/stacks
SCAN_DEPTH=1
CORS_ALLOW_ORIGINS=https://seu-frontend.com.br,http://localhost:5173
APP_PORT=8004
```

`CORS_ALLOW_ORIGINS` aceita lista separada por virgula. Use `*` para liberar todas as origens.

## Subindo o Postgres local (opcional)

```bash
docker compose up -d postgres
```

## Instalacao e execucao

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m scripts.run_api
```

`APP_PORT` define em qual porta a API sobe na VPS.

## Rodar coleta manual

Via API:

```bash
curl -X POST http://localhost:8000/collect
```

Via script:

```bash
python -m scripts.run_collection
```

## Endpoints principais

- `GET /health`
- `POST /collect`
- `GET /runs?limit=20`
- `GET /usage/latest`
- `GET /usage/latest/summary` (total por instalacao e total geral em GB)
- `GET /usage/latest/file-types` (categorias por instalacao no ultimo run)
- `GET /usage/latest/file-types/by-url?url=https://instancia.exemplo.com` (retorna apenas a instalacao da URL)

Observacao: a rota `/` nao esta definida e retorna `404`. Use os endpoints acima ou `/docs`.

## Exemplo de consulta por URL

```bash
curl "http://localhost:8000/usage/latest/file-types/by-url?url=https://cliente-a.exemplo.com"
```

## Exemplo de resposta de resumo

```json
{
  "run_id": "6d5b88d4-a73f-4f01-9b3e-6f13e8f5db9d",
  "scanned_at": "2026-03-10T14:30:12.345678+00:00",
  "total_bytes": 14567890123,
  "total_gb": 13.566,
  "installations": [
    {
      "installation_name": "cliente_a",
      "installation_path": "/data/apps/cliente_a",
      "total_bytes": 22334455,
      "total_gb": 0.021
    },
    {
      "installation_name": "cliente_b",
      "installation_path": "/opt/stacks/cliente_b",
      "total_bytes": 14545555668,
      "total_gb": 13.545
    }
  ]
}
```

## Agendamento com cron (a cada 30 minutos)

```bash
*/30 * * * * cd /home/angelo/projects/size-manager && /home/angelo/projects/size-manager/.venv/bin/python -m scripts.run_collection >> /var/log/size-manager.log 2>&1
```

## Deploy com GitHub Actions

O workflow foi criado em [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) e faz:

- Validacao no push para `main` (instala dependencias e roda `compileall`).
- Deploy via SSH no servidor apos validacao bem-sucedida.

### Secrets necessarios no GitHub

No repositorio, configure em **Settings > Secrets and variables > Actions**:

- `SSH_HOST`: host do servidor (ex.: `203.0.113.10`)
- `SSH_PORT`: porta SSH (ex.: `22`)
- `SSH_USER`: usuario SSH
- `SSH_PRIVATE_KEY`: chave privada para acesso ao servidor
- `DEPLOY_PATH`: caminho do projeto no servidor (ex.: `/home/deploy/size-manager`)
- `DEPLOY_COMMAND`: comando final de restart/reload (ex.: `sudo systemctl restart size-manager`)

Na VPS, configure o arquivo `.env` com `APP_PORT` para definir a porta da API.
Exemplo:

```env
APP_PORT=8004
```

Se seu deploy sobe o processo Python diretamente, um exemplo de `DEPLOY_COMMAND` e:

```bash
if [ -f app.pid ] && kill -0 "$(cat app.pid)" 2>/dev/null; then
  kill "$(cat app.pid)"
  sleep 1
fi
nohup .venv/bin/python3 -m scripts.run_api > app.log 2>&1 &
echo $! > app.pid
```

### Comportamento do deploy

No servidor remoto, o pipeline executa:

```bash
cd $DEPLOY_PATH
git fetch --all
git checkout main
git pull --ff-only origin main
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
$DEPLOY_COMMAND
```
