from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

import torch

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_DIR = BACKEND_DIR.parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from results_tracker import ResultsTracker


def evaluation_env() -> dict:
    env = os.environ.copy()
    env.setdefault("TORCH_HOME", str(BACKEND_DIR / ".cache" / "torch"))
    env.setdefault("MPLCONFIGDIR", str(BACKEND_DIR / ".cache" / "matplotlib"))
    Path(env["TORCH_HOME"]).mkdir(parents=True, exist_ok=True)
    Path(env["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)
    return env


def resolve_checkpoint_from_metrics(metrics: dict, fallback: str) -> str:
    checkpoint = metrics.get("checkpoint_path")
    return checkpoint if isinstance(checkpoint, str) and checkpoint else fallback


def run_image_evaluation(
    evaluator_script: str,
    input_image: str,
    style_ids: List[str],
    devices: List[str],
    tracker: ResultsTracker,
) -> None:
    print("\n" + "=" * 80)
    print("EVALUATING IMAGE STYLE TRANSFER")
    print("=" * 80 + "\n")

    env = evaluation_env()
    for style_id in style_ids:
        for device in devices:
            print(f"Evaluating {style_id} on {device}...", end=" ", flush=True)
            with tempfile.NamedTemporaryFile(
                prefix="image_eval_",
                suffix=".json",
                delete=False,
                dir=str(tracker.results_dir),
            ) as handle:
                json_path = Path(handle.name)
            try:
                cmd = [
                    sys.executable,
                    evaluator_script,
                    "image",
                    "--input",
                    input_image,
                    "--style-id",
                    style_id,
                    "--device",
                    device,
                    "--json-out",
                    str(json_path),
                ]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=240,
                    cwd=str(REPO_DIR),
                    env=env,
                )
                if result.returncode != 0:
                    print("FAILED")
                    print(result.stderr or result.stdout)
                    continue

                metrics = json.loads(json_path.read_text(encoding="utf-8"))
                checkpoint = resolve_checkpoint_from_metrics(
                    metrics,
                    fallback=f"style:{style_id}",
                )
                tracker.add_result(
                    mode="Image",
                    checkpoint=checkpoint,
                    device=device,
                    fps=metrics.get("fps"),
                    psnr=metrics.get("psnr_to_input"),
                    mae=metrics.get("mae_to_input"),
                    lpips=metrics.get("lpips"),
                    notes=f"Style: {style_id}",
                    metadata=metrics,
                )
                print("OK")
            except subprocess.TimeoutExpired:
                print("TIMEOUT")
            except Exception as exc:
                print(f"ERROR: {exc}")
            finally:
                json_path.unlink(missing_ok=True)


def run_video_evaluation(
    evaluator_script: str,
    input_video: str,
    devices: List[str],
    tracker: ResultsTracker,
) -> None:
    print("\n" + "=" * 80)
    print("EVALUATING VIDEO STYLE TRANSFER")
    print("=" * 80 + "\n")

    env = evaluation_env()
    for device in devices:
        print(f"Evaluating video on {device}...", end=" ", flush=True)
        with tempfile.NamedTemporaryFile(
            prefix="video_eval_",
            suffix=".json",
            delete=False,
            dir=str(tracker.results_dir),
        ) as handle:
            json_path = Path(handle.name)
        try:
            plot_path = tracker.results_dir / f"temporal_{device}.png"
            cmd = [
                sys.executable,
                evaluator_script,
                "video",
                "--input",
                input_video,
                "--device",
                device,
                "--max-metric-frames",
                "60",
                "--json-out",
                str(json_path),
                "--save-plot",
                str(plot_path),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                cwd=str(REPO_DIR),
                env=env,
            )
            if result.returncode != 0:
                print("FAILED")
                print(result.stderr or result.stdout)
                continue

            metrics = json.loads(json_path.read_text(encoding="utf-8"))
            checkpoint = resolve_checkpoint_from_metrics(
                metrics,
                fallback="style_transfer/reco/reconet.pth",
            )
            tracker.add_result(
                mode="Video",
                checkpoint=checkpoint,
                device=device,
                fps=metrics.get("effective_fps"),
                twe=metrics.get("temporal_warping_error_mae"),
                notes=f"Frames: {metrics.get('temporal_pairs_evaluated', 0)}",
                metadata=metrics,
            )
            print("OK")
        except subprocess.TimeoutExpired:
            print("TIMEOUT")
        except Exception as exc:
            print(f"ERROR: {exc}")
        finally:
            json_path.unlink(missing_ok=True)


def generate_reports(tracker: ResultsTracker) -> None:
    print("\n" + "=" * 80)
    print("GENERATING REPORTS")
    print("=" * 80 + "\n")

    print("Summary:")
    tracker.print_summary()

    print("\nGenerating plots...", end=" ", flush=True)
    tracker.plot_fps_comparison()
    tracker.plot_quality_metrics()
    tracker.plot_video_temporal_stability()
    tracker.plot_device_comparison()
    print("Done")

    print("Generating HTML report...", end=" ", flush=True)
    report_path = tracker.generate_report()
    print(f"Done ({report_path})")

    print("Saving results...", end=" ", flush=True)
    json_path = tracker.save_json()
    csv_path = tracker.save_csv()
    print(f"Done ({json_path}, {csv_path})")


def main() -> None:
    evaluator_script = str(SCRIPT_DIR / "evaluate_style_transfer.py")
    input_image = str(REPO_DIR / "frontend" / "public" / "home" / "styled1.jpg")
    input_video = str(REPO_DIR / "test_data" / "sample.mp4")
    styles = ["starry-night", "mosaic", "wave", "udnie"]
    devices = ["cpu", "cuda"] if torch.cuda.is_available() else ["cpu"]

    if not Path(evaluator_script).exists():
        print(f"Evaluator script not found: {evaluator_script}")
        raise SystemExit(1)

    if not Path(input_image).exists():
        print(f"Sample image not found: {input_image}")
        raise SystemExit(1)

    if not Path(input_video).exists():
        print(f"Sample video not found: {input_video}")
        print("Skipping video evaluation")
        input_video = ""

    tracker = ResultsTracker(results_dir=str(BACKEND_DIR / "evaluation" / "results"))
    run_image_evaluation(evaluator_script, input_image, styles, devices, tracker)
    if input_video:
        run_video_evaluation(evaluator_script, input_video, devices, tracker)
    generate_reports(tracker)

    print("\n" + "=" * 80)
    print("EVALUATION COMPLETE")
    print("=" * 80)
    print(f"Results directory: {tracker.results_dir}")


if __name__ == "__main__":
    main()
