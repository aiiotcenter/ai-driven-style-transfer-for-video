import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.cache import cache

JOB_TTL_SECONDS = 3600


def _job_key(job_id: str) -> str:
    return f"job_{job_id}"


def _job_dir() -> Path:
    root = Path(getattr(settings, "BASE_DIR", Path.cwd()))
    return root / ".webcam_jobs"


def _job_file(job_id: str) -> Path:
    return _job_dir() / f"{job_id}.json"


def _read_file_state(job_id: str) -> Optional[Dict[str, Any]]:
    path = _job_file(job_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _write_file_state(job_id: str, payload: Dict[str, Any]) -> None:
    directory = _job_dir()
    directory.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=directory,
        prefix=f"{job_id}.",
        suffix=".tmp",
        delete=False,
    ) as temp_file:
        json.dump(payload, temp_file)
        temp_path = Path(temp_file.name)

    os.replace(temp_path, _job_file(job_id))


def get_job_state(job_id: str) -> Optional[Dict[str, Any]]:
    try:
        cached = cache.get(_job_key(job_id))
        if cached:
            return cached
    except Exception:
        pass
    return _read_file_state(job_id)


def set_job_state(job_id: str, payload: Dict[str, Any]) -> None:
    try:
        cache.set(_job_key(job_id), payload, timeout=JOB_TTL_SECONDS)
    except Exception:
        pass
    _write_file_state(job_id, payload)


def update_job_state(job_id: str, **payload: Any) -> Dict[str, Any]:
    current = get_job_state(job_id) or {}
    current.update(payload)
    set_job_state(job_id, current)
    return current
