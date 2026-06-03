from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional


def reconet_model_candidates(base_dir: Path) -> List[Path]:
    candidates: List[Path] = []
    env_path = os.environ.get("RECONET_MODEL_PATH")
    if env_path:
        candidates.append(Path(env_path).expanduser())

    candidates.append(base_dir / "style_transfer" / "reco" / "reconet.pth")
    candidates.append(base_dir / "models" / "reconet" / "reconet.pth")

    # Preserve order, deduplicate.
    deduped: List[Path] = []
    seen = set()
    for candidate in candidates:
        normalized = candidate.resolve(strict=False)
        if normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return deduped


def resolve_existing_reconet_model(base_dir: Path) -> Optional[str]:
    for candidate in reconet_model_candidates(base_dir):
        if candidate.exists() and candidate.is_file() and candidate.stat().st_size > 0:
            return str(candidate)
    return None


def preferred_reconet_model_path(base_dir: Path) -> str:
    existing = resolve_existing_reconet_model(base_dir)
    if existing:
        return existing
    return str(reconet_model_candidates(base_dir)[0])
