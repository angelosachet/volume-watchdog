from __future__ import annotations

import subprocess
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from app.config import settings
from app.database import get_db


@dataclass
class UsageRecord:
    installation_name: str
    installation_path: str
    volume_name: str
    size_bytes: int
    backend_url: str | None


BACKEND_URL_PATTERNS = (
    re.compile(r"^\s*-\s*BACKEND_URL\s*=\s*(?P<value>.+?)\s*$"),
    re.compile(r"^\s*BACKEND_URL\s*:\s*(?P<value>.+?)\s*$"),
)


def _normalize_env_value(raw_value: str) -> str | None:
    value = raw_value.strip().strip('"').strip("'")
    return value or None


def _extract_backend_url(installation_path: Path) -> str | None:
    compose_path = installation_path / "docker-compose.yml"
    if not compose_path.exists() or not compose_path.is_file():
        return None

    try:
        content = compose_path.read_text(encoding="utf-8")
    except OSError:
        return None

    for line in content.splitlines():
        for pattern in BACKEND_URL_PATTERNS:
            match = pattern.match(line)
            if match:
                return _normalize_env_value(match.group("value"))

    return None


def _du_bytes_for_volumes(volumes_path: Path) -> list[tuple[str, int]]:
    entries = [entry for entry in volumes_path.iterdir()]
    if not entries:
        return []

    cmd = ["du", "-sb", *[str(entry) for entry in entries]]
    result = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        # No volume directories or inaccessible path.
        return []

    rows: list[tuple[str, int]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue

        size_str, entry_path = parts
        try:
            size_bytes = int(size_str)
        except ValueError:
            continue

        rows.append((Path(entry_path).name, size_bytes))

    return rows


def _discover_installations_under_root(root_path: Path, max_depth: int) -> list[Path]:
    installations: list[Path] = []
    queue: deque[tuple[Path, int]] = deque([(root_path, 0)])

    while queue:
        current_path, depth = queue.popleft()
        volumes_path = current_path / "volumes"

        if volumes_path.exists() and volumes_path.is_dir():
            installations.append(current_path)
            continue

        if depth >= max_depth:
            continue

        for child in current_path.iterdir():
            if child.is_dir():
                queue.append((child, depth + 1))

    return installations


def find_installations() -> list[Path]:
    installations: list[Path] = []
    max_depth = max(0, settings.scan_depth)

    for root in settings.normalized_roots:
        root_path = Path(root)
        if not root_path.exists() or not root_path.is_dir():
            continue

        installations.extend(_discover_installations_under_root(root_path, max_depth))

    return installations


def collect_usage_records() -> list[UsageRecord]:
    records: list[UsageRecord] = []

    for installation_path in find_installations():
        volumes_path = installation_path / "volumes"
        volumes = _du_bytes_for_volumes(volumes_path)
        backend_url = _extract_backend_url(installation_path)

        for volume_name, size_bytes in volumes:
            records.append(
                UsageRecord(
                    installation_name=installation_path.name,
                    installation_path=str(installation_path),
                    volume_name=volume_name,
                    size_bytes=size_bytes,
                    backend_url=backend_url,
                )
            )

    return records


def save_scan(records: list[UsageRecord]) -> tuple[UUID, datetime]:
    run_id = uuid4()
    scanned_at = datetime.now(timezone.utc)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scan_runs (run_id, scanned_at, root_paths)
                VALUES (%s, %s, %s)
                """,
                (run_id, scanned_at, settings.normalized_roots),
            )

            if records:
                cur.executemany(
                    """
                    INSERT INTO volume_usage (
                        run_id,
                        installation_name,
                        installation_path,
                        volume_name,
                        size_bytes,
                        backend_url
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            run_id,
                            rec.installation_name,
                            rec.installation_path,
                            rec.volume_name,
                            rec.size_bytes,
                            rec.backend_url,
                        )
                        for rec in records
                    ],
                )
        conn.commit()

    return run_id, scanned_at


def run_collection() -> tuple[UUID, datetime, int]:
    records = collect_usage_records()
    run_id, scanned_at = save_scan(records)
    return run_id, scanned_at, len(records)
