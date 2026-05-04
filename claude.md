# Como este sistema funciona

Este projeto e uma API **FastAPI** para monitorar uso de disco de instalacoes (volumes Docker) e guardar historico no Postgres.

## Fluxo principal

1. Na inicializacao, a API executa `init_db()` e garante schema.
2. Em `POST /collect`, o coletor:
   - procura instalacoes com pasta `volumes/` dentro de `ROOT_PATHS` ate `SCAN_DEPTH`
   - mede cada volume com `du -sb`
   - calcula uso por tipo de arquivo (fotos, videos, audios, textos, outros)
   - tenta extrair `BACKEND_URL` de `docker-compose.yml`/`.env`
3. Persiste um novo `run_id` com dados agregados e detalhados no banco.

## Endpoints principais

- `GET /health`
- `POST /collect`
- `GET /runs`
- `GET /usage/latest`
- `GET /usage/latest/summary`
- `GET /usage/latest/file-types`
- `GET /usage/latest/file-types/by-url?url=...`

## Componentes

- `app/collector.py`: descoberta de instalacoes e coleta.
- `app/main.py`: API e consultas.
- `app/database.py`: conexao e criacao de tabelas.
- `scripts/run_api.py` e `scripts/run_collection.py`: execucao via script/cron.

## Estrutura

```
size-manager/
├── app/
│   ├── main.py        # rotas FastAPI
│   ├── collector.py   # descoberta + medicao + categorizacao
│   ├── database.py    # conexao + init schema
│   ├── config.py      # Pydantic Settings sobre .env
│   └── schemas.py     # modelos Pydantic
├── scripts/
│   ├── run_api.py        # Uvicorn em 0.0.0.0:APP_PORT
│   └── run_collection.py # roda 1 coleta e imprime run_id
├── docker-compose.yml    # Postgres 16 + volume pgdata
└── requirements.txt      # FastAPI, Uvicorn, psycopg3, pydantic-settings
```

## Variaveis de ambiente

| Variavel | Tipo | Obrigatoria | Padrao | Uso |
|----------|------|-------------|--------|-----|
| `DATABASE_URL` | string | sim | — | `postgresql://user:pass@host:port/db` |
| `ROOT_PATHS` | CSV | nao | `/data/apps,/opt/stacks` | raizes onde buscar instalacoes |
| `SCAN_DEPTH` | int | nao | `1` | profundidade maxima (0 = so root) |
| `CORS_ALLOW_ORIGINS` | CSV | nao | `*` | origens CORS |
| `APP_PORT` | int | nao | `8004` | porta do Uvicorn |

## Schema do banco

`scan_runs` (`run_id` UUID PK, `scanned_at` timestamptz, `root_paths` text[]).

`volume_usage` (FK `run_id` ON DELETE CASCADE; `installation_name`, `installation_path`, `volume_name`, `size_bytes` BIGINT, `backend_url`).

`installation_filetype_usage` (FK `run_id`; `installation_name/path/backend_url`; `photos_bytes`, `videos_bytes`, `audios_bytes`, `texts_bytes`, `others_bytes`).

Indices em `run_id`, `installation_path`, `backend_url`.

## Categorizacao de arquivos (`collector.py:_categorize_extension`)

- **fotos**: `jpg`, `jpeg`, `png`, `gif`, `webp`, `bmp`
- **videos**: `mp4`, `mkv`, `avi`, `mov`, `webm`
- **audios**: `mp3`, `wav`, `flac`, `aac`
- **textos**: `txt`, `md`, `log`, `csv`, `json`
- **outros**: tudo o que nao casar acima

Walk com `Path.rglob("*")`; volume total via `du -sb`.

## Extracao de `BACKEND_URL`

1. Le `docker-compose.yml` (`- BACKEND_URL=...` ou `BACKEND_URL: ...`).
2. Fallback: `.env` no diretorio da instalacao.
3. Resolve `${VAR:-default}`.
4. Normaliza: prefixa `https://` se faltar, remove porta default, padroniza host.

## Modos de execucao

```bash
# Servidor (Swagger em /docs)
python3 -m scripts.run_api

# Coleta unica (cron)
python3 -m scripts.run_collection
# saida: run_id=<uuid> scanned_at=<ISO8601> scanned_items=<n>
```

Cron a cada 30 min:

```cron
*/30 * * * * cd /caminho && .venv/bin/python3 -m scripts.run_collection >> coleta.log 2>&1
```

## Exemplos de chamadas

```bash
curl http://localhost:8004/health
curl -X POST http://localhost:8004/collect
curl http://localhost:8004/runs?limit=20
curl http://localhost:8004/usage/latest
curl http://localhost:8004/usage/latest/summary
curl http://localhost:8004/usage/latest/file-types
curl "http://localhost:8004/usage/latest/file-types/by-url?url=https://cliente-a.exemplo.com"
```

