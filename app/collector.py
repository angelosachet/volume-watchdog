from __future__ import annotations

import subprocess
import re
from collections import defaultdict
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse
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


@dataclass
class FileTypeUsageRecord:
    installation_name: str
    installation_path: str
    backend_url: str | None
    photos_bytes: int
    videos_bytes: int
    audios_bytes: int
    texts_bytes: int
    others_bytes: int


PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "bmp"}
VIDEO_EXTENSIONS = {"mp4", "mkv", "avi", "mov", "webm"}
AUDIO_EXTENSIONS = {"mp3", "wav", "flac", "aac"}
TEXT_EXTENSIONS = {"txt", "md", "log", "csv", "json"}


BACKEND_URL_PATTERNS = (
    re.compile(r"^\s*-\s*BACKEND_URL\s*=\s*(?P<value>.+?)\s*$"),
    re.compile(r"^\s*BACKEND_URL\s*:\s*(?P<value>.+?)\s*$"),
)

ENV_FILE_PATTERN = re.compile(r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*?)\s*$")
ENV_REFERENCE_PATTERN = re.compile(
    r"^\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:(?P<sep>:-|-)(?P<default>.*))?\}$"
)


def _normalize_env_value(raw_value: str) -> str | None:
    value = raw_value.strip().strip('"').strip("'")
    return value or None


def _read_env_values(installation_path: Path) -> dict[str, str]:
    env_path = installation_path / ".env"
    if not env_path.exists() or not env_path.is_file():
        return {}

    try:
        content = env_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    values: dict[str, str] = {}
    for line in content.splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue

        match = ENV_FILE_PATTERN.match(stripped_line)
        if not match:
            continue

        parsed_value = _normalize_env_value(match.group("value"))
        if parsed_value is None:
            continue

        values[match.group("key")] = parsed_value

    return values


def _resolve_compose_env_value(raw_value: str, env_values: dict[str, str]) -> str | None:
    normalized_value = _normalize_env_value(raw_value)
    if not normalized_value:
        return None

    env_reference = ENV_REFERENCE_PATTERN.match(normalized_value)
    if not env_reference:
        return normalized_value

    env_name = env_reference.group("name")
    resolved_value = _normalize_env_value(env_values.get(env_name, ""))
    if resolved_value:
        return resolved_value

    default_value = env_reference.group("default")
    if default_value is None:
        return None

    return _normalize_env_value(default_value)


def normalize_backend_url(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None

    normalized_value = _normalize_env_value(raw_value)
    if not normalized_value:
        return None

    if ENV_REFERENCE_PATTERN.match(normalized_value):
        return None

    candidate = normalized_value
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None

    hostname = parsed.hostname.lower()
    port_segment = f":{parsed.port}" if parsed.port else ""
    auth_segment = ""
    if parsed.username:
        auth_segment = parsed.username
        if parsed.password:
            auth_segment = f"{auth_segment}:{parsed.password}"
        auth_segment = f"{auth_segment}@"

    normalized_path = parsed.path.rstrip("/")
    if normalized_path == "/":
        normalized_path = ""

    return urlunparse(
        (
            parsed.scheme.lower(),
            f"{auth_segment}{hostname}{port_segment}",
            normalized_path,
            "",
            "",
            "",
        )
    )


def backend_url_match_key(raw_value: str | None) -> str | None:
    normalized_url = normalize_backend_url(raw_value)
    if not normalized_url:
        return None

    parsed = urlparse(normalized_url)
    if not parsed.hostname:
        return None

    normalized_path = parsed.path.rstrip("/")
    host_segment = parsed.hostname.lower()
    if parsed.port:
        host_segment = f"{host_segment}:{parsed.port}"

    return f"{host_segment}{normalized_path}".lower()


def _extract_backend_url(installation_path: Path) -> str | None:
    compose_path = installation_path / "docker-compose.yml"
    if not compose_path.exists() or not compose_path.is_file():
        env_values = _read_env_values(installation_path)
        return normalize_backend_url(env_values.get("BACKEND_URL"))

    try:
        content = compose_path.read_text(encoding="utf-8")
    except OSError:
        return None

    env_values = _read_env_values(installation_path)

    for line in content.splitlines():
        for pattern in BACKEND_URL_PATTERNS:
            match = pattern.match(line)
            if match:
                resolved_value = _resolve_compose_env_value(match.group("value"), env_values)
                normalized_url = normalize_backend_url(resolved_value)
                if normalized_url:
                    return normalized_url

    return normalize_backend_url(env_values.get("BACKEND_URL"))


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


def _categorize_extension(ext: str) -> str:
    normalized = ext.lower().lstrip(".")
    if normalized in PHOTO_EXTENSIONS:
        return "photos"
    if normalized in VIDEO_EXTENSIONS:
        return "videos"
    if normalized in AUDIO_EXTENSIONS:
        return "audios"
    if normalized in TEXT_EXTENSIONS:
        return "texts"
    return "others"


def _collect_file_type_usage_for_installation(installation_path: Path) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)

    try:
        for file_path in installation_path.rglob("*"):
            if not file_path.is_file():
                continue

            try:
                file_size = file_path.stat().st_size
            except OSError:
                continue

            category = _categorize_extension(file_path.suffix)
            totals[category] += file_size
    except OSError:
        pass

    return {
        "photos": int(totals.get("photos", 0)),
        "videos": int(totals.get("videos", 0)),
        "audios": int(totals.get("audios", 0)),
        "texts": int(totals.get("texts", 0)),
        "others": int(totals.get("others", 0)),
    }


def collect_file_type_usage_records() -> list[FileTypeUsageRecord]:
    records: list[FileTypeUsageRecord] = []

    for installation_path in find_installations():
        backend_url = _extract_backend_url(installation_path)
        categorized = _collect_file_type_usage_for_installation(installation_path)

        records.append(
            FileTypeUsageRecord(
                installation_name=installation_path.name,
                installation_path=str(installation_path),
                backend_url=backend_url,
                photos_bytes=categorized["photos"],
                videos_bytes=categorized["videos"],
                audios_bytes=categorized["audios"],
                texts_bytes=categorized["texts"],
                others_bytes=categorized["others"],
            )
        )

    return records


def save_scan(
    records: list[UsageRecord],
    file_type_records: list[FileTypeUsageRecord],
) -> tuple[UUID, datetime]:
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

            if file_type_records:
                cur.executemany(
                    """
                    INSERT INTO installation_filetype_usage (
                        run_id,
                        installation_name,
                        installation_path,
                        backend_url,
                        photos_bytes,
                        videos_bytes,
                        audios_bytes,
                        texts_bytes,
                        others_bytes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            run_id,
                            rec.installation_name,
                            rec.installation_path,
                            rec.backend_url,
                            rec.photos_bytes,
                            rec.videos_bytes,
                            rec.audios_bytes,
                            rec.texts_bytes,
                            rec.others_bytes,
                        )
                        for rec in file_type_records
                    ],
                )
        conn.commit()

    return run_id, scanned_at


def run_collection() -> tuple[UUID, datetime, int]:
    records = collect_usage_records()
    file_type_records = collect_file_type_usage_records()
    run_id, scanned_at = save_scan(records, file_type_records)
    return run_id, scanned_at, len(records)
