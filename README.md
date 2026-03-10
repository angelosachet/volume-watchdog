# Volume Watchdog

Sistema para varrer instalacoes Docker dentro de diretorios raiz configurados, salvar uso de disco no Postgres e consultar via API.

## O que ele faz

- Procura instalacoes (pastas que tenham `volumes/`) dentro de cada raiz configurada.
- Usa `ROOT_PATHS` do `.env` para definir quais diretorios raiz devem ser varridos.
- Usa `SCAN_DEPTH` do `.env` para controlar ate quantos niveis abaixo de cada raiz a busca vai.
- Executa `du -sb <instalacao>/volumes/*` para obter tamanho real em bytes.
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
```

## Subindo o Postgres local (opcional)

```bash
docker compose up -d postgres
```

## Instalacao e execucao

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

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
