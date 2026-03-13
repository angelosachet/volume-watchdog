from datetime import datetime

from pydantic import BaseModel


class VolumeUsageItem(BaseModel):
    installation_name: str
    installation_path: str
    volume_name: str
    size_bytes: int
    size_gb: float
    backend_url: str | None = None


class RunSummary(BaseModel):
    run_id: str
    scanned_at: datetime
    root_paths: list[str]


class CollectResponse(BaseModel):
    run_id: str
    scanned_items: int
    scanned_at: datetime


class LatestUsageResponse(BaseModel):
    run_id: str
    scanned_at: datetime
    items: list[VolumeUsageItem]


class InstallationSummary(BaseModel):
    installation_name: str
    installation_path: str
    total_bytes: int
    total_gb: float
    backend_url: str | None = None


class LatestSummaryResponse(BaseModel):
    run_id: str
    scanned_at: datetime
    total_bytes: int
    total_gb: float
    installations: list[InstallationSummary]
