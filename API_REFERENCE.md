# API Reference - Volume Watchdog

Base URL (local): `http://localhost:8000`

Observacoes:
- Todos os endpoints retornam JSON.
- Quando ainda nao existe nenhuma coleta, endpoints de consulta do ultimo run retornam `404` com `detail` em portugues.

## Health

### GET /health
Verifica se a API esta ativa.

Exemplo:
```bash
curl -s http://localhost:8000/health
```

Resposta 200:
```json
{
  "status": "ok"
}
```

## Coleta

### POST /collect
Executa uma coleta imediatamente e salva um novo run no banco.

Exemplo:
```bash
curl -s -X POST http://localhost:8000/collect
```

Resposta 200:
```json
{
  "run_id": "6d5b88d4-a73f-4f01-9b3e-6f13e8f5db9d",
  "scanned_items": 42,
  "scanned_at": "2026-04-01T15:00:00.000000+00:00"
}
```

## Runs

### GET /runs
Lista execucoes de coleta em ordem decrescente de data.

Query params:
- `limit` (opcional, inteiro): quantidade de runs retornados.
- Minimo: `1`
- Maximo: `500`
- Padrao: `20`

Exemplo:
```bash
curl -s "http://localhost:8000/runs?limit=20"
```

Resposta 200:
```json
[
  {
    "run_id": "6d5b88d4-a73f-4f01-9b3e-6f13e8f5db9d",
    "scanned_at": "2026-04-01T15:00:00.000000+00:00",
    "root_paths": ["/data/apps", "/opt/stacks"]
  }
]
```

## Uso por Volume (ultimo run)

### GET /usage/latest
Retorna todos os volumes do ultimo run, com tamanho em bytes e GB.

Exemplo:
```bash
curl -s http://localhost:8000/usage/latest
```

Resposta 200:
```json
{
  "run_id": "6d5b88d4-a73f-4f01-9b3e-6f13e8f5db9d",
  "scanned_at": "2026-04-01T15:00:00.000000+00:00",
  "items": [
    {
      "installation_name": "cliente_a",
      "installation_path": "/data/apps/cliente_a",
      "volume_name": "db_data",
      "size_bytes": 123456789,
      "size_gb": 0.115,
      "backend_url": "https://cliente-a.exemplo.com"
    }
  ]
}
```

Resposta 404 (sem coleta):
```json
{
  "detail": "Nenhuma coleta encontrada"
}
```

### GET /usage/latest/summary
Retorna resumo agregado do ultimo run por instalacao e total geral.

Exemplo:
```bash
curl -s http://localhost:8000/usage/latest/summary
```

Resposta 200:
```json
{
  "run_id": "6d5b88d4-a73f-4f01-9b3e-6f13e8f5db9d",
  "scanned_at": "2026-04-01T15:00:00.000000+00:00",
  "total_bytes": 14567890123,
  "total_gb": 13.566,
  "installations": [
    {
      "installation_name": "cliente_a",
      "installation_path": "/data/apps/cliente_a",
      "total_bytes": 22334455,
      "total_gb": 0.021,
      "backend_url": "https://cliente-a.exemplo.com"
    }
  ]
}
```

Resposta 404 (sem coleta):
```json
{
  "detail": "Nenhuma coleta encontrada"
}
```

## Uso por Tipo de Arquivo (ultimo run)

Categorias calculadas:
- fotos: `jpg`, `jpeg`, `png`, `gif`, `webp`, `bmp`
- videos: `mp4`, `mkv`, `avi`, `mov`, `webm`
- audios: `mp3`, `wav`, `flac`, `aac`
- textos: `txt`, `md`, `log`, `csv`, `json`
- outros: tudo que nao entra nas categorias acima

### GET /usage/latest/file-types
Retorna os totais por tipo de arquivo para cada instalacao no ultimo run.

Exemplo:
```bash
curl -s http://localhost:8000/usage/latest/file-types
```

Resposta 200:
```json
{
  "run_id": "6d5b88d4-a73f-4f01-9b3e-6f13e8f5db9d",
  "scanned_at": "2026-04-01T15:00:00.000000+00:00",
  "installations": [
    {
      "installation_name": "cliente_a",
      "installation_path": "/data/apps/cliente_a",
      "backend_url": "https://cliente-a.exemplo.com",
      "photos_bytes": 1048576,
      "photos_mb": 1.0,
      "videos_bytes": 0,
      "videos_mb": 0.0,
      "audios_bytes": 0,
      "audios_mb": 0.0,
      "texts_bytes": 2048,
      "texts_mb": 0.0,
      "others_bytes": 8192,
      "others_mb": 0.01,
      "total_bytes": 1058816,
      "total_mb": 1.01
    }
  ]
}
```

Resposta 404 (sem coleta):
```json
{
  "detail": "Nenhuma coleta encontrada"
}
```

### GET /usage/latest/file-types/by-url
Retorna somente a instalacao cuja `backend_url` bate com a URL informada.

Query params:
- `url` (obrigatorio, string, minimo 1 caractere)

Exemplo:
```bash
curl -s "http://localhost:8000/usage/latest/file-types/by-url?url=https://cliente-a.exemplo.com"
```

Resposta 200:
```json
{
  "run_id": "6d5b88d4-a73f-4f01-9b3e-6f13e8f5db9d",
  "scanned_at": "2026-04-01T15:00:00.000000+00:00",
  "data": {
    "installation_name": "cliente_a",
    "installation_path": "/data/apps/cliente_a",
    "backend_url": "https://cliente-a.exemplo.com",
    "photos_bytes": 1048576,
    "photos_mb": 1.0,
    "videos_bytes": 0,
    "videos_mb": 0.0,
    "audios_bytes": 0,
    "audios_mb": 0.0,
    "texts_bytes": 2048,
    "texts_mb": 0.0,
    "others_bytes": 8192,
    "others_mb": 0.01,
    "total_bytes": 1058816,
    "total_mb": 1.01
  }
}
```

Resposta 404 (sem coleta):
```json
{
  "detail": "Nenhuma coleta encontrada"
}
```

Resposta 404 (URL nao encontrada no ultimo run):
```json
{
  "detail": "Nenhuma instalacao encontrada para a URL informada"
}
```

## OpenAPI e Swagger

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
