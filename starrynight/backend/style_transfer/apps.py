import os
from pathlib import Path
from typing import Dict, List, Optional

from django.apps import AppConfig

from .fast_style import load_model


def scan_models(model_dir: Path) -> Dict[str, List[str]]:
    models = {}
    for root, _subfolders, files in os.walk(model_dir):
        for file in files:
            if models.get(Path(root).name):
                if file.endswith(".pth"):
                    models[Path(root).name].append(str(Path(root) / file))
            else:
                if file.endswith(".pth"):
                    models[Path(root).name] = [str(Path(root) / file)]
    return models


class StyleTransferConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "style_transfer"

    _models_dir = Path(__file__).resolve().parents[1] / "models"
    model_paths = scan_models(_models_dir)
    models: Dict[str, object] = {}

    @classmethod
    def refresh_model_paths(cls) -> Dict[str, List[str]]:
        cls.model_paths = scan_models(cls._models_dir)
        return cls.model_paths

    @classmethod
    def get_loaded_model(cls, model_path: str) -> Optional[object]:
        cached = cls.models.get(model_path)
        if cached is not None:
            return cached

        resolved_path = Path(model_path).resolve(strict=False)
        if not resolved_path.exists():
            return None

        loaded_model = load_model(str(resolved_path))
        cls.models[str(resolved_path)] = loaded_model
        if str(resolved_path) != model_path:
            cls.models[model_path] = loaded_model
        return loaded_model
