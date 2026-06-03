from __future__ import annotations

import csv
import html
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib.pyplot as plt


@dataclass
class ResultRow:
    mode: str
    checkpoint: str
    device: str
    fps: Optional[float] = None
    psnr: Optional[float] = None
    mae: Optional[float] = None
    lpips: Optional[float] = None
    twe: Optional[float] = None
    notes: str = ""
    metadata: Dict[str, object] = field(default_factory=dict)


class ResultsTracker:
    def __init__(self, results_dir: str = "evaluation/results") -> None:
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.results: List[ResultRow] = []

    def add_result(
        self,
        mode: str,
        checkpoint: str,
        device: str,
        fps: Optional[float] = None,
        psnr: Optional[float] = None,
        mae: Optional[float] = None,
        lpips: Optional[float] = None,
        twe: Optional[float] = None,
        notes: str = "",
        metadata: Optional[Dict[str, object]] = None,
    ) -> None:
        self.results.append(
            ResultRow(
                mode=mode,
                checkpoint=checkpoint,
                device=device,
                fps=fps,
                psnr=psnr,
                mae=mae,
                lpips=lpips,
                twe=twe,
                notes=notes,
                metadata=metadata or {},
            )
        )

    def _require_results(self) -> bool:
        if self.results:
            return True
        print("No evaluation results recorded yet.")
        return False

    def _path(self, stem: str, suffix: str) -> Path:
        return self.results_dir / f"{stem}_{self.timestamp}.{suffix}"

    def print_summary(self) -> None:
        if not self._require_results():
            return
        print("Mode   Device  FPS    PSNR    MAE     LPIPS   TWE      Checkpoint")
        for row in self.results:
            print(
                f"{row.mode:<6} "
                f"{row.device:<6} "
                f"{self._fmt(row.fps):<6} "
                f"{self._fmt(row.psnr):<7} "
                f"{self._fmt(row.mae):<7} "
                f"{self._fmt(row.lpips):<7} "
                f"{self._fmt(row.twe):<8} "
                f"{row.checkpoint}"
            )

    @staticmethod
    def _fmt(value: Optional[float], digits: int = 3) -> str:
        if value is None:
            return "-"
        return f"{value:.{digits}f}"

    def save_json(self) -> Path:
        path = self._path("results", "json")
        payload = {
            "timestamp": self.timestamp,
            "results": [asdict(item) for item in self.results],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def save_csv(self) -> Path:
        path = self._path("results", "csv")
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "mode",
                    "checkpoint",
                    "device",
                    "fps",
                    "psnr",
                    "mae",
                    "lpips",
                    "twe",
                    "notes",
                    "metadata",
                ],
            )
            writer.writeheader()
            for item in self.results:
                row = asdict(item)
                row["metadata"] = json.dumps(row["metadata"], sort_keys=True)
                writer.writerow(row)
        return path

    def plot_fps_comparison(self) -> Optional[Path]:
        if not self._require_results():
            return None
        rows = [row for row in self.results if row.fps is not None]
        if not rows:
            return None
        labels = [f"{row.mode}:{Path(row.checkpoint).name}\n{row.device}" for row in rows]
        values = [row.fps for row in rows]
        fig, ax = plt.subplots(figsize=(max(8, len(rows) * 1.5), 5))
        ax.bar(labels, values, color="#3b82f6")
        ax.set_ylabel("FPS")
        ax.set_title("FPS Comparison")
        ax.tick_params(axis="x", rotation=30)
        plt.tight_layout()
        path = self._path("fps_comparison", "png")
        plt.savefig(path, dpi=150)
        plt.close(fig)
        return path

    def plot_quality_metrics(self) -> Optional[Path]:
        if not self._require_results():
            return None
        rows = [row for row in self.results if row.mode.lower() == "image"]
        if not rows:
            return None
        labels = [Path(row.checkpoint).name for row in rows]
        x = range(len(rows))
        fig, ax = plt.subplots(figsize=(max(8, len(rows) * 1.5), 5))
        psnr = [row.psnr or 0.0 for row in rows]
        mae = [row.mae or 0.0 for row in rows]
        lpips = [row.lpips or 0.0 for row in rows]
        ax.plot(x, psnr, marker="o", label="PSNR")
        ax.plot(x, mae, marker="o", label="MAE")
        ax.plot(x, lpips, marker="o", label="LPIPS")
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.set_title("Image Quality Metrics")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        path = self._path("quality_metrics", "png")
        plt.savefig(path, dpi=150)
        plt.close(fig)
        return path

    def plot_video_temporal_stability(self) -> Optional[Path]:
        if not self._require_results():
            return None
        rows = [row for row in self.results if row.mode.lower() == "video" and row.twe is not None]
        if not rows:
            return None
        labels = [f"{row.device}:{Path(row.checkpoint).name}" for row in rows]
        values = [row.twe for row in rows]
        fig, ax = plt.subplots(figsize=(max(8, len(rows) * 1.5), 5))
        ax.bar(labels, values, color="#ef4444")
        ax.set_ylabel("Temporal Warping Error (MAE)")
        ax.set_title("Video Temporal Stability")
        ax.tick_params(axis="x", rotation=20)
        plt.tight_layout()
        path = self._path("temporal_stability", "png")
        plt.savefig(path, dpi=150)
        plt.close(fig)
        return path

    def plot_device_comparison(self) -> Optional[Path]:
        if not self._require_results():
            return None
        grouped: Dict[str, List[ResultRow]] = defaultdict(list)
        for row in self.results:
            grouped[row.device].append(row)
        if not grouped:
            return None
        devices = list(grouped.keys())
        avg_fps = [
            sum((row.fps or 0.0) for row in rows) / max(1, len([row for row in rows if row.fps is not None]))
            if any(row.fps is not None for row in rows)
            else 0.0
            for rows in grouped.values()
        ]
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(devices, avg_fps, color="#10b981")
        ax.set_ylabel("Average FPS")
        ax.set_title("Device Comparison")
        plt.tight_layout()
        path = self._path("device_comparison", "png")
        plt.savefig(path, dpi=150)
        plt.close(fig)
        return path

    def generate_report(self) -> Path:
        image_paths = [
            self._path("fps_comparison", "png"),
            self._path("quality_metrics", "png"),
            self._path("temporal_stability", "png"),
            self._path("device_comparison", "png"),
        ]
        available_images = [path for path in image_paths if path.exists()]
        table_rows = "\n".join(
            "<tr>"
            f"<td>{html.escape(row.mode)}</td>"
            f"<td>{html.escape(row.device)}</td>"
            f"<td>{html.escape(row.checkpoint)}</td>"
            f"<td>{self._fmt(row.fps)}</td>"
            f"<td>{self._fmt(row.psnr)}</td>"
            f"<td>{self._fmt(row.mae)}</td>"
            f"<td>{self._fmt(row.lpips)}</td>"
            f"<td>{self._fmt(row.twe)}</td>"
            f"<td>{html.escape(row.notes)}</td>"
            "</tr>"
            for row in self.results
        )
        image_blocks = "\n".join(
            f'<div><h3>{html.escape(path.stem)}</h3><img src="{html.escape(path.name)}" style="max-width:100%;border:1px solid #ccc;" /></div>'
            for path in available_images
        )
        report = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>StarryNight Evaluation Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #f5f5f5; }}
    img {{ margin-bottom: 24px; }}
  </style>
</head>
<body>
  <h1>StarryNight Evaluation Report</h1>
  <p>Generated: {html.escape(self.timestamp)}</p>
  <table>
    <thead>
      <tr>
        <th>Mode</th><th>Device</th><th>Checkpoint</th><th>FPS</th>
        <th>PSNR</th><th>MAE</th><th>LPIPS</th><th>TWE</th><th>Notes</th>
      </tr>
    </thead>
    <tbody>
      {table_rows}
    </tbody>
  </table>
  {image_blocks}
</body>
</html>
"""
        path = self._path("report", "html")
        path.write_text(report, encoding="utf-8")
        return path
