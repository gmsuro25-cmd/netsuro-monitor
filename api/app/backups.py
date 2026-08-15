import json
import os
from datetime import datetime, timezone
from pathlib import Path


BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/backups"))


def _timestamp(value: float) -> datetime:
    return datetime.fromtimestamp(value, tz=timezone.utc)


def get_backup_summary() -> dict:
    retention_days = int(os.environ.get("BACKUP_RETENTION_DAYS", "14"))
    if not BACKUP_DIR.exists():
        return {
            "available": False,
            "count": 0,
            "total_size_bytes": 0,
            "retention_days": retention_days,
            "latest": None,
            "recent": [],
            "last_verification": None,
        }

    files = sorted(
        BACKUP_DIR.glob("netsuro-*.dump"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    records = [
        {
            "name": path.name,
            "size_bytes": path.stat().st_size,
            "created_at": _timestamp(path.stat().st_mtime),
        }
        for path in files
    ]

    verification = None
    marker = BACKUP_DIR / ".last-verified"
    if marker.exists():
        try:
            data = json.loads(marker.read_text())
            verification = {
                "backup_name": Path(data["file"]).name,
                "verified_at": datetime.fromisoformat(
                    data["verified_at"].replace("Z", "+00:00")
                ),
            }
        except (KeyError, OSError, ValueError, json.JSONDecodeError):
            verification = None

    return {
        "available": True,
        "count": len(records),
        "total_size_bytes": sum(item["size_bytes"] for item in records),
        "retention_days": retention_days,
        "latest": records[0] if records else None,
        "recent": records[:5],
        "last_verification": verification,
    }
