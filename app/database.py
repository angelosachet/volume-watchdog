from __future__ import annotations

from contextlib import contextmanager

from psycopg import Connection, connect
from psycopg.rows import dict_row

from app.config import settings


@contextmanager
def get_db() -> Connection:
    with connect(settings.database_url, row_factory=dict_row) as conn:
        yield conn


def init_db() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS scan_runs (
        run_id UUID PRIMARY KEY,
        scanned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        root_paths TEXT[] NOT NULL
    );

    CREATE TABLE IF NOT EXISTS volume_usage (
        id BIGSERIAL PRIMARY KEY,
        run_id UUID NOT NULL REFERENCES scan_runs(run_id) ON DELETE CASCADE,
        installation_name TEXT NOT NULL,
        installation_path TEXT NOT NULL,
        volume_name TEXT NOT NULL,
        size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
        backend_url TEXT
    );

    CREATE TABLE IF NOT EXISTS installation_filetype_usage (
        id BIGSERIAL PRIMARY KEY,
        run_id UUID NOT NULL REFERENCES scan_runs(run_id) ON DELETE CASCADE,
        installation_name TEXT NOT NULL,
        installation_path TEXT NOT NULL,
        backend_url TEXT,
        photos_bytes BIGINT NOT NULL DEFAULT 0 CHECK (photos_bytes >= 0),
        videos_bytes BIGINT NOT NULL DEFAULT 0 CHECK (videos_bytes >= 0),
        audios_bytes BIGINT NOT NULL DEFAULT 0 CHECK (audios_bytes >= 0),
        texts_bytes BIGINT NOT NULL DEFAULT 0 CHECK (texts_bytes >= 0),
        others_bytes BIGINT NOT NULL DEFAULT 0 CHECK (others_bytes >= 0)
    );

    ALTER TABLE volume_usage
    ADD COLUMN IF NOT EXISTS backend_url TEXT;

    CREATE INDEX IF NOT EXISTS idx_volume_usage_installation
        ON volume_usage (installation_name, installation_path);

    CREATE INDEX IF NOT EXISTS idx_volume_usage_run_id
        ON volume_usage (run_id);

    CREATE INDEX IF NOT EXISTS idx_filetype_usage_run_id
        ON installation_filetype_usage (run_id);

    CREATE INDEX IF NOT EXISTS idx_filetype_usage_backend_url
        ON installation_filetype_usage (backend_url);
    """

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()
