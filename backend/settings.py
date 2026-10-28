"""Resource limits; all sizes are per job, including intermediate files."""
from dataclasses import dataclass
import os
from pathlib import Path


def positive(name, default):
    value = int(os.getenv(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class Settings:
    max_bytes: int = positive("MAX_FILE_MB", 500) * 1024 * 1024
    max_duration: int = positive("MAX_DURATION_SECONDS", 1800)
    max_items: int = positive("MAX_ITEMS", 100)
    workers: int = positive("MAX_CONCURRENT_JOBS", 2)
    queue_size: int = positive("MAX_QUEUED_JOBS", 10)
    max_storage: int = positive("MAX_STORAGE_MB", 2048) * 1024 * 1024
    max_history: int = positive("MAX_JOB_HISTORY", 100)
    ttl: int = positive("FILE_TTL_SECONDS", 3600)
    timeout: int = positive("JOB_TIMEOUT_SECONDS", 1800)
    info_timeout: int = positive("INFO_TIMEOUT_SECONDS", 120)
    root: Path = Path(os.getenv("DOWNLOAD_DIR", "downloads")).resolve()
    browser: str = os.getenv("COOKIES_BROWSER", "")


settings = Settings()
