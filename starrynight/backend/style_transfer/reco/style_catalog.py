from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_STYLE_ID = "starry-night"

STYLE_LABELS = {
    "starry-night": "Van Gogh - Starry Night",
    "mosaic": "Gaudi - Mosaic",
    "udnie": "Francis Picabia - Udnie",
    "wave": "Hokusai - Great Wave",
    "tokyo-ghoul": "Tokyo Ghoul",
    "lazy": "Lazy Sunday",
    "bayanihan": "Bayanihan",
}

STYLE_MODEL_CANDIDATES = {
    "starry-night": [
        ("models", "starry", "starry80.pth"),
        ("models", "starry", "starry_dark.pth"),
    ],
    "mosaic": [
        ("models", "mosiac", "mosaic_light.pth"),
        ("models", "mosiac", "mosaic_aggressive.pth"),
    ],
    "udnie": [
        ("models", "udnie_aggressive.pth"),
    ],
    "wave": [
        ("models", "wave", "wave100.pth"),
        ("models", "wave", "wave50.pth"),
        ("models", "wave", "wave150.pth"),
        ("models", "wave", "wave200.pth"),
    ],
    "tokyo-ghoul": [
        ("models", "tokyo_ghoul", "tokyo_ghoul_light.pth"),
        ("models", "tokyo_ghoul", "tokyo_ghoul_aggressive.pth"),
    ],
    "lazy": [
        ("models", "lazy", "lazy250.pth"),
    ],
    "bayanihan": [
        ("models", "bayanihan100.pth"),
    ],
}


def _normalize_style_id(raw: str) -> str:
    return raw.strip().lower().replace("_", "-").replace(" ", "-")


def _label_for(style_id: str) -> str:
    return STYLE_LABELS.get(style_id, style_id.replace("-", " ").title())


def _resolve_candidate(base_dir: Path, candidate_parts: Tuple[str, ...]) -> Path:
    return (base_dir / Path(*candidate_parts)).resolve(strict=False)


def style_model_map(base_dir: Path) -> Dict[str, Path]:
    model_map: Dict[str, Path] = {}
    for style_id, candidates in STYLE_MODEL_CANDIDATES.items():
        for candidate in candidates:
            model_path = _resolve_candidate(base_dir, candidate)
            if model_path.exists() and model_path.is_file() and model_path.stat().st_size > 0:
                model_map[style_id] = model_path
                break

    if not model_map:
        # Expose at least the default expected path for clear API feedback.
        first_default = STYLE_MODEL_CANDIDATES[DEFAULT_STYLE_ID][0]
        model_map[DEFAULT_STYLE_ID] = _resolve_candidate(base_dir, first_default)

    return model_map


def available_styles(base_dir: Path) -> Tuple[List[Dict[str, str]], str]:
    mapped = style_model_map(base_dir)
    default_style = DEFAULT_STYLE_ID if DEFAULT_STYLE_ID in mapped else next(iter(mapped.keys()))

    styles: List[Dict[str, str]] = []
    for style_id, model_path in mapped.items():
        styles.append(
            {
                "id": style_id,
                "label": _label_for(style_id),
                "available": model_path.exists() and model_path.is_file() and model_path.stat().st_size > 0,
                "model_path": str(model_path),
            }
        )
    styles.sort(key=lambda item: (item["id"] != default_style, item["label"]))
    return styles, default_style


def resolve_style_model(base_dir: Path, style_id: Optional[str]) -> Tuple[str, str]:
    mapped = style_model_map(base_dir)
    normalized = _normalize_style_id(style_id or "")
    if not normalized:
        normalized = DEFAULT_STYLE_ID if DEFAULT_STYLE_ID in mapped else next(iter(mapped.keys()))

    if normalized not in mapped:
        valid = ", ".join(sorted(mapped.keys()))
        raise ValueError(f"Unknown style '{normalized}'. Available styles: {valid}")

    model_path = mapped[normalized]
    if not model_path.exists() or not model_path.is_file() or model_path.stat().st_size <= 0:
        raise FileNotFoundError(
            f"Style model for '{normalized}' is missing at: {model_path}"
        )

    return str(model_path), normalized
