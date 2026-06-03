from __future__ import annotations

import hashlib
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def format_size(size_bytes: int) -> str:
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def verify_file(path: Path, min_size_mb: float) -> None:
    if not path.exists():
        raise SystemExit(f"Missing required file: {path}")
    size_bytes = path.stat().st_size
    if size_bytes < int(min_size_mb * 1024 * 1024):
        raise SystemExit(
            f"File too small: {path} ({format_size(size_bytes)}), expected >= {min_size_mb:.2f} MB"
        )
    print(f"OK  {path}")
    print(f"    Size: {format_size(size_bytes)}")
    print(f"    SHA256: {sha256(path)}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    onnx_path = repo_root / "frontend" / "public" / "models" / "pointilism-10.onnx"
    reconet_path = repo_root / "backend" / "style_transfer" / "reco" / "reconet.pth"

    print("Verifying required model assets...")
    verify_file(onnx_path, min_size_mb=5.0)
    verify_file(reconet_path, min_size_mb=5.0)
    print("Model asset verification passed.")


if __name__ == "__main__":
    main()
