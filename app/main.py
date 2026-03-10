from fastapi import FastAPI, HTTPException, Query

from app.collector import run_collection
from app.database import get_db, init_db
from app.schemas import (
    CollectResponse,
    InstallationSummary,
    LatestSummaryResponse,
    LatestUsageResponse,
    RunSummary,
    VolumeUsageItem,
)

app = FastAPI(title="Size Manager API", version="1.0.0")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


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
                SELECT installation_name, installation_path, volume_name, size_bytes
                FROM volume_usage
                WHERE run_id = %s
                ORDER BY installation_path, volume_name
                """,
                (run_row["run_id"],),
            )
            rows = cur.fetchall()

    items = [
        VolumeUsageItem(
            **row,
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
                SELECT installation_name, installation_path, SUM(size_bytes) AS total_bytes
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
