from contextlib import asynccontextmanager
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.collector import backend_url_match_key, normalize_backend_url, run_collection
from app.config import settings
from app.database import get_db, init_db
from app.schemas import (
    CollectResponse,
    FileTypeUsageByInstallation,
    FileTypeUsageByUrlResponse,
    InstallationSummary,
    LatestFileTypeUsageResponse,
    LatestSummaryResponse,
    LatestUsageResponse,
    RunSummary,
    VolumeUsageItem,
)

_scheduler = BackgroundScheduler()


def _scheduled_collect() -> None:
    try:
        run_id, _, scanned_items = run_collection()
        print(f"[scheduler] collected run_id={run_id} scanned_items={scanned_items}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[scheduler] collection failed: {exc}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    interval = settings.collect_interval_minutes
    if interval > 0:
        _scheduler.add_job(
            _scheduled_collect,
            IntervalTrigger(minutes=interval),
            id="collect",
            next_run_time=datetime.now(),
            max_instances=1,
            coalesce=True,
        )
        _scheduler.start()
    try:
        yield
    finally:
        if _scheduler.running:
            _scheduler.shutdown(wait=False)


app = FastAPI(title="Size Manager API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.normalized_cors_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/collect", response_model=CollectResponse)
def collect_now() -> CollectResponse:
    run_id, scanned_at, scanned_items = run_collection()
    return CollectResponse(run_id=str(run_id), scanned_at=scanned_at, scanned_items=scanned_items)


@app.get("/runs", response_model=list[RunSummary])
def list_runs(limit: int = Query(default=20, ge=1, le=500)) -> list[RunSummary]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id::text AS run_id, scanned_at, root_paths
                FROM scan_runs
                ORDER BY scanned_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

    return [RunSummary(**row) for row in rows]


@app.get("/usage/latest", response_model=LatestUsageResponse)
def latest_usage() -> LatestUsageResponse:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id::text AS run_id, scanned_at
                FROM scan_runs
                ORDER BY scanned_at DESC
                LIMIT 1
                """
            )
            run_row = cur.fetchone()

            if not run_row:
                raise HTTPException(status_code=404, detail="Nenhuma coleta encontrada")

            cur.execute(
                """
                SELECT installation_name, installation_path, volume_name, size_bytes, backend_url
                FROM volume_usage
                WHERE run_id = %s
                ORDER BY installation_path, volume_name
                """,
                (run_row["run_id"],),
            )
            rows = cur.fetchall()

    items = [
        VolumeUsageItem(
            **{
                **row,
                "backend_url": normalize_backend_url(row["backend_url"]),
            },
            size_gb=round(row["size_bytes"] / (1024**3), 3),
        )
        for row in rows
    ]

    return LatestUsageResponse(
        run_id=run_row["run_id"],
        scanned_at=run_row["scanned_at"],
        items=items,
    )


@app.get("/usage/latest/summary", response_model=LatestSummaryResponse)
def latest_usage_summary() -> LatestSummaryResponse:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id::text AS run_id, scanned_at
                FROM scan_runs
                ORDER BY scanned_at DESC
                LIMIT 1
                """
            )
            run_row = cur.fetchone()

            if not run_row:
                raise HTTPException(status_code=404, detail="Nenhuma coleta encontrada")

            cur.execute(
                """
                SELECT
                    installation_name,
                    installation_path,
                    MAX(backend_url) AS backend_url,
                    SUM(size_bytes) AS total_bytes
                FROM volume_usage
                WHERE run_id = %s
                GROUP BY installation_name, installation_path
                ORDER BY installation_path
                """,
                (run_row["run_id"],),
            )
            rows = cur.fetchall()

    installations = [
        InstallationSummary(
            installation_name=row["installation_name"],
            installation_path=row["installation_path"],
            total_bytes=row["total_bytes"],
            total_gb=round(row["total_bytes"] / (1024**3), 3),
            backend_url=normalize_backend_url(row["backend_url"]),
        )
        for row in rows
    ]
    total_bytes = sum(item.total_bytes for item in installations)

    return LatestSummaryResponse(
        run_id=run_row["run_id"],
        scanned_at=run_row["scanned_at"],
        total_bytes=total_bytes,
        total_gb=round(total_bytes / (1024**3), 3),
        installations=installations,
    )


def _build_file_type_item(row: dict) -> FileTypeUsageByInstallation:
    total_bytes = (
        row["photos_bytes"]
        + row["videos_bytes"]
        + row["audios_bytes"]
        + row["texts_bytes"]
        + row["others_bytes"]
    )

    return FileTypeUsageByInstallation(
        installation_name=row["installation_name"],
        installation_path=row["installation_path"],
        backend_url=normalize_backend_url(row["backend_url"]),
        photos_bytes=row["photos_bytes"],
        photos_mb=round(row["photos_bytes"] / (1024**2), 2),
        videos_bytes=row["videos_bytes"],
        videos_mb=round(row["videos_bytes"] / (1024**2), 2),
        audios_bytes=row["audios_bytes"],
        audios_mb=round(row["audios_bytes"] / (1024**2), 2),
        texts_bytes=row["texts_bytes"],
        texts_mb=round(row["texts_bytes"] / (1024**2), 2),
        others_bytes=row["others_bytes"],
        others_mb=round(row["others_bytes"] / (1024**2), 2),
        total_bytes=total_bytes,
        total_mb=round(total_bytes / (1024**2), 2),
    )


@app.get("/usage/latest/file-types", response_model=LatestFileTypeUsageResponse)
def latest_file_type_usage() -> LatestFileTypeUsageResponse:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id::text AS run_id, scanned_at
                FROM scan_runs
                ORDER BY scanned_at DESC
                LIMIT 1
                """
            )
            run_row = cur.fetchone()

            if not run_row:
                raise HTTPException(status_code=404, detail="Nenhuma coleta encontrada")

            cur.execute(
                """
                SELECT
                    installation_name,
                    installation_path,
                    backend_url,
                    photos_bytes,
                    videos_bytes,
                    audios_bytes,
                    texts_bytes,
                    others_bytes
                FROM installation_filetype_usage
                WHERE run_id = %s
                ORDER BY installation_path
                """,
                (run_row["run_id"],),
            )
            rows = cur.fetchall()

    items = [_build_file_type_item(row) for row in rows]
    return LatestFileTypeUsageResponse(
        run_id=run_row["run_id"],
        scanned_at=run_row["scanned_at"],
        installations=items,
    )


@app.get("/usage/latest/file-types/by-url", response_model=FileTypeUsageByUrlResponse)
def latest_file_type_usage_by_url(url: str = Query(..., min_length=1)) -> FileTypeUsageByUrlResponse:
    requested_url_key = backend_url_match_key(url)
    if not requested_url_key:
        raise HTTPException(status_code=400, detail="URL informada invalida")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id::text AS run_id, scanned_at
                FROM scan_runs
                ORDER BY scanned_at DESC
                LIMIT 1
                """
            )
            run_row = cur.fetchone()

            if not run_row:
                raise HTTPException(status_code=404, detail="Nenhuma coleta encontrada")

            cur.execute(
                """
                SELECT
                    installation_name,
                    installation_path,
                    backend_url,
                    photos_bytes,
                    videos_bytes,
                    audios_bytes,
                    texts_bytes,
                    others_bytes
                FROM installation_filetype_usage
                WHERE run_id = %s
                ORDER BY installation_path
                """,
                (run_row["run_id"],),
            )
            rows = cur.fetchall()

    row = next(
        (
            item
            for item in rows
            if backend_url_match_key(item["backend_url"]) == requested_url_key
        ),
        None,
    )

    if not row:
        raise HTTPException(status_code=404, detail="Nenhuma instalacao encontrada para a URL informada")

    return FileTypeUsageByUrlResponse(
        run_id=run_row["run_id"],
        scanned_at=run_row["scanned_at"],
        data=_build_file_type_item(row),
    )
