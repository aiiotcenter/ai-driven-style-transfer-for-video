from __future__ import annotations

import argparse
import os
import json
import tempfile
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import torch


REPO_BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = REPO_BACKEND_DIR.parent
CACHE_DIR = REPO_BACKEND_DIR / ".cache"

import sys

if str(REPO_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_BACKEND_DIR))

os.environ.setdefault("TORCH_HOME", str(CACHE_DIR / "torch"))
os.environ.setdefault("MPLCONFIGDIR", str(CACHE_DIR / "matplotlib"))
(CACHE_DIR / "torch").mkdir(parents=True, exist_ok=True)
(CACHE_DIR / "matplotlib").mkdir(parents=True, exist_ok=True)

from style_transfer.fast_style import utils as fast_utils
from style_transfer.fast_style.api import stlye_transfer
from style_transfer.fast_style.stylize import load_model as load_fast_style_model
from style_transfer.reco.model_utils import preferred_reconet_model_path, resolve_existing_reconet_model
from style_transfer.reco.reco_infer import load_model as load_reconet_model
from style_transfer.reco.reco_infer import stylize_video
from style_transfer.reco.style_catalog import DEFAULT_STYLE_ID, available_styles, resolve_style_model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate StarryNight style-transfer checkpoints for image and video workflows.",
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    image_parser = subparsers.add_parser("image", help="Evaluate a fast-style image checkpoint.")
    image_parser.add_argument("--input", required=True, help="Input image path.")
    image_parser.add_argument("--style-ref", help="Optional style reference image path for visualization only.")
    image_parser.add_argument("--style-id", default=DEFAULT_STYLE_ID, help="Style id from the backend catalog.")
    image_parser.add_argument("--model-path", help="Optional explicit .pth checkpoint path.")
    image_parser.add_argument("--device", default=default_device(), help="cpu or cuda.")
    image_parser.add_argument("--fps-iters", type=int, default=50, help="Iterations for FPS timing.")
    image_parser.add_argument("--warmup-iters", type=int, default=10, help="Warmup iterations before timing.")
    image_parser.add_argument("--save-output", help="Optional path to save the stylized image.")
    image_parser.add_argument(
        "--save-visualization",
        help="Optional path to save a side-by-side comparison image.",
    )
    image_parser.add_argument("--json-out", help="Optional path to write JSON metrics.")
    image_parser.add_argument("--output-json", dest="json_out", help=argparse.SUPPRESS)

    video_parser = subparsers.add_parser("video", help="Evaluate the ReCoNet video checkpoint.")
    video_parser.add_argument("--input", required=True, help="Input video path.")
    video_parser.add_argument("--model-path", help="Optional explicit ReCoNet checkpoint path.")
    video_parser.add_argument("--device", default=default_device(), help="cpu or cuda.")
    video_parser.add_argument(
        "--target-fps",
        type=float,
        default=None,
        help="Optional output target FPS passed through stylize_video.",
    )
    video_parser.add_argument(
        "--max-metric-frames",
        type=int,
        default=120,
        help="Max stylized frame pairs to scan for temporal metrics.",
    )
    video_parser.add_argument("--save-output", help="Optional path to save the stylized video.")
    video_parser.add_argument(
        "--save-plot",
        help="Optional path to save a temporal stability plot.",
    )
    video_parser.add_argument("--json-out", help="Optional path to write JSON metrics.")
    video_parser.add_argument("--output-json", dest="json_out", help=argparse.SUPPRESS)

    return parser.parse_args()


def default_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def resolve_fast_style_checkpoint(base_dir: Path, style_id: str, model_path: Optional[str]) -> Path:
    if model_path:
        resolved = Path(model_path).expanduser().resolve(strict=False)
        if not resolved.exists():
            raise FileNotFoundError(f"Fast-style checkpoint not found: {resolved}")
        return resolved

    resolved_path, normalized_style = resolve_style_model(base_dir, style_id)
    print(f"Using fast-style checkpoint for '{normalized_style}': {resolved_path}")
    return Path(resolved_path)


def resolve_reconet_checkpoint(base_dir: Path, model_path: Optional[str]) -> Path:
    if model_path:
        resolved = Path(model_path).expanduser().resolve(strict=False)
        if not resolved.exists():
            raise FileNotFoundError(f"ReCoNet checkpoint not found: {resolved}")
        return resolved

    existing = resolve_existing_reconet_model(base_dir)
    if not existing:
        raise FileNotFoundError(
            "ReCoNet checkpoint not found. Expected something like "
            f"{preferred_reconet_model_path(base_dir)}"
        )
    print(f"Using ReCoNet checkpoint: {existing}")
    return Path(existing)


def load_bgr_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    if image is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    return image


def bgr_to_rgb(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def image_to_lpips_tensor(rgb_image: np.ndarray, device: str) -> torch.Tensor:
    tensor = (
        torch.from_numpy(rgb_image)
        .permute(2, 0, 1)
        .unsqueeze(0)
        .float()
        .to(device)
        / 127.5
        - 1.0
    )
    return tensor


def maybe_compute_lpips(original_rgb: np.ndarray, stylized_rgb: np.ndarray, device: str) -> Optional[float]:
    try:
        import lpips
    except ImportError:
        return None

    loss_fn = lpips.LPIPS(net="vgg").to(device)
    with torch.no_grad():
        score = loss_fn(
            image_to_lpips_tensor(original_rgb, device),
            image_to_lpips_tensor(stylized_rgb, device),
        )
    return float(score.item())


def compute_psnr(original_bgr: np.ndarray, stylized_bgr: np.ndarray) -> float:
    mse = float(np.mean((original_bgr.astype(np.float32) - stylized_bgr.astype(np.float32)) ** 2))
    if mse <= 1e-12:
        return float("inf")
    return float(20.0 * np.log10(255.0 / np.sqrt(mse)))


def compute_mae(original_bgr: np.ndarray, stylized_bgr: np.ndarray) -> float:
    return float(np.mean(np.abs(original_bgr.astype(np.float32) - stylized_bgr.astype(np.float32))))


def summarize_available_styles(base_dir: Path) -> List[Dict[str, object]]:
    styles, default_style = available_styles(base_dir)
    for item in styles:
        item["is_default"] = item["id"] == default_style
    return styles


def render_triptych(
    original_rgb: np.ndarray,
    stylized_rgb: np.ndarray,
    style_rgb: Optional[np.ndarray],
    save_path: Optional[Path],
) -> None:
    if save_path is None:
        return

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Skipping visualization save because matplotlib is not installed.")
        return

    ensure_parent(save_path)
    columns = 3 if style_rgb is not None else 2
    fig, axes = plt.subplots(1, columns, figsize=(5 * columns, 5))
    if columns == 2:
        axes = list(axes)
    axes[0].imshow(original_rgb)
    axes[0].set_title("Original")
    axes[0].axis("off")
    axes[1].imshow(stylized_rgb)
    axes[1].set_title("Stylized")
    axes[1].axis("off")
    if style_rgb is not None:
        axes[2].imshow(style_rgb)
        axes[2].set_title("Style Reference")
        axes[2].axis("off")
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close(fig)


def print_json(metrics: Dict[str, object], json_out: Optional[Path]) -> None:
    payload = json.dumps(metrics, indent=2, sort_keys=True)
    print(payload)
    if json_out is not None:
        ensure_parent(json_out)
        json_out.write_text(payload + "\n", encoding="utf-8")


def measure_fast_style_fps(
    model: torch.nn.Module,
    input_bgr: np.ndarray,
    device: str,
    warmup_iters: int,
    fps_iters: int,
) -> float:
    content_tensor = fast_utils.itot(input_bgr).to(device)
    model.eval()
    with torch.no_grad():
        for _ in range(max(0, warmup_iters)):
            _ = model(content_tensor)
        start = time.perf_counter()
        for _ in range(max(1, fps_iters)):
            _ = model(content_tensor)
        elapsed = time.perf_counter() - start
    return float(max(1, fps_iters) / max(elapsed, 1e-9))


def evaluate_image(args: argparse.Namespace) -> Dict[str, object]:
    base_dir = REPO_BACKEND_DIR
    input_path = Path(args.input).expanduser().resolve(strict=False)
    style_ref_path = Path(args.style_ref).expanduser().resolve(strict=False) if args.style_ref else None
    checkpoint_path = resolve_fast_style_checkpoint(base_dir, args.style_id, args.model_path)

    model = load_fast_style_model(str(checkpoint_path)).to(args.device).eval()
    original_bgr = load_bgr_image(input_path)
    stylized_bgr = stlye_transfer(model=model, content=original_bgr).clip(0, 255).astype("uint8")

    fps = measure_fast_style_fps(
        model=model,
        input_bgr=original_bgr,
        device=args.device,
        warmup_iters=args.warmup_iters,
        fps_iters=args.fps_iters,
    )
    original_rgb = bgr_to_rgb(original_bgr)
    stylized_rgb = bgr_to_rgb(stylized_bgr)
    style_rgb = bgr_to_rgb(load_bgr_image(style_ref_path)) if style_ref_path else None
    lpips_score = maybe_compute_lpips(original_rgb, stylized_rgb, args.device)
    mae = compute_mae(original_bgr, stylized_bgr)
    psnr = compute_psnr(original_bgr, stylized_bgr)

    if args.save_output:
        save_output = Path(args.save_output).expanduser().resolve(strict=False)
        ensure_parent(save_output)
        cv2.imwrite(str(save_output), stylized_bgr)

    if args.save_visualization:
        render_triptych(
            original_rgb=original_rgb,
            stylized_rgb=stylized_rgb,
            style_rgb=style_rgb,
            save_path=Path(args.save_visualization).expanduser().resolve(strict=False),
        )

    metrics: Dict[str, object] = {
        "mode": "image",
        "device": args.device,
        "input_path": str(input_path),
        "checkpoint_path": str(checkpoint_path),
        "available_styles": summarize_available_styles(base_dir),
        "image_shape_bgr": list(original_bgr.shape),
        "fps": fps,
        "lpips": lpips_score,
        "mae_to_input": mae,
        "psnr_to_input": psnr,
        "lpips_available": lpips_score is not None,
    }

    print("\nImage Evaluation")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"FPS: {fps:.2f}")
    print(f"MAE to input: {mae:.2f}")
    print(f"PSNR to input: {psnr:.2f} dB")
    if lpips_score is None:
        print("LPIPS: unavailable (`pip install lpips` to enable)")
    else:
        print(f"LPIPS: {lpips_score:.4f}")

    return metrics


def video_frame_iterator(path: Path) -> Iterable[np.ndarray]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {path}")
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            yield frame
    finally:
        capture.release()


def dense_flow(frame_t_bgr: np.ndarray, frame_t1_bgr: np.ndarray) -> np.ndarray:
    gray_t = cv2.cvtColor(frame_t_bgr, cv2.COLOR_BGR2GRAY)
    gray_t1 = cv2.cvtColor(frame_t1_bgr, cv2.COLOR_BGR2GRAY)
    return cv2.calcOpticalFlowFarneback(
        gray_t,
        gray_t1,
        None,
        pyr_scale=0.5,
        levels=3,
        winsize=15,
        iterations=3,
        poly_n=5,
        poly_sigma=1.2,
        flags=0,
    )


def warp_frame_with_flow(frame_bgr: np.ndarray, flow: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    height, width = flow.shape[:2]
    grid_x, grid_y = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    map_x = grid_x + flow[:, :, 0]
    map_y = grid_y + flow[:, :, 1]
    warped = cv2.remap(
        frame_bgr,
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT101,
    )
    valid = (
        (map_x >= 0.0)
        & (map_x <= (width - 1))
        & (map_y >= 0.0)
        & (map_y <= (height - 1))
    )
    return warped, valid


def temporal_metrics(
    source_video_path: Path,
    stylized_video_path: Path,
    max_metric_frames: int,
) -> Dict[str, object]:
    source_iter = video_frame_iterator(source_video_path)
    stylized_iter = video_frame_iterator(stylized_video_path)

    try:
        prev_source = next(source_iter)
        prev_stylized = next(stylized_iter)
    except StopIteration:
        return {
            "pairs_evaluated": 0,
            "temporal_warping_error_mae": None,
            "temporal_warping_error_mse": None,
            "naive_frame_diff_mae": None,
            "series": [],
        }

    if prev_source.shape[:2] != prev_stylized.shape[:2]:
        prev_source = cv2.resize(
            prev_source,
            (prev_stylized.shape[1], prev_stylized.shape[0]),
            interpolation=cv2.INTER_AREA,
        )

    naive_diffs: List[float] = []
    warp_mae_scores: List[float] = []
    warp_mse_scores: List[float] = []

    for pair_index, (next_source, next_stylized) in enumerate(zip(source_iter, stylized_iter), start=1):
        if pair_index > max_metric_frames:
            break
        if next_source.shape[:2] != next_stylized.shape[:2]:
            next_source = cv2.resize(
                next_source,
                (next_stylized.shape[1], next_stylized.shape[0]),
                interpolation=cv2.INTER_AREA,
            )
        flow = dense_flow(prev_source, next_source)
        warped_prev, valid_mask = warp_frame_with_flow(prev_stylized, flow)

        valid_mask_3 = np.repeat(valid_mask[:, :, None], 3, axis=2)
        warped_valid = warped_prev.astype(np.float32)[valid_mask_3]
        next_valid = next_stylized.astype(np.float32)[valid_mask_3]

        if warped_valid.size == 0:
            prev_source = next_source
            prev_stylized = next_stylized
            continue

        delta = warped_valid - next_valid
        warp_mae_scores.append(float(np.mean(np.abs(delta))))
        warp_mse_scores.append(float(np.mean(delta ** 2)))
        naive_diffs.append(
            float(
                np.mean(
                    np.abs(prev_stylized.astype(np.float32) - next_stylized.astype(np.float32))
                )
            )
        )

        prev_source = next_source
        prev_stylized = next_stylized

    return {
        "pairs_evaluated": len(warp_mae_scores),
        "temporal_warping_error_mae": float(np.mean(warp_mae_scores)) if warp_mae_scores else None,
        "temporal_warping_error_mse": float(np.mean(warp_mse_scores)) if warp_mse_scores else None,
        "naive_frame_diff_mae": float(np.mean(naive_diffs)) if naive_diffs else None,
        "series": warp_mae_scores,
    }


def maybe_save_temporal_plot(series: Sequence[float], save_path: Optional[Path]) -> None:
    if save_path is None or not series:
        return
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Skipping temporal plot save because matplotlib is not installed.")
        return

    ensure_parent(save_path)
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(series, linewidth=2)
    ax.set_title("Temporal Warping Error (MAE)")
    ax.set_xlabel("Frame Pair")
    ax.set_ylabel("Warped Difference")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close(fig)


def evaluate_video(args: argparse.Namespace) -> Dict[str, object]:
    base_dir = REPO_BACKEND_DIR
    input_path = Path(args.input).expanduser().resolve(strict=False)
    checkpoint_path = resolve_reconet_checkpoint(base_dir, args.model_path)

    temp_output_dir: Optional[tempfile.TemporaryDirectory[str]] = None
    if args.save_output:
        output_path = Path(args.save_output).expanduser().resolve(strict=False)
        ensure_parent(output_path)
    else:
        temp_output_dir = tempfile.TemporaryDirectory(prefix="style_eval_video_")
        output_path = Path(temp_output_dir.name) / "stylized.mp4"

    model = load_reconet_model(str(checkpoint_path), device=args.device)
    start = time.perf_counter()
    result = stylize_video(
        input_path=input_path,
        output_path=output_path,
        model=model,
        target_fps=args.target_fps,
    )
    elapsed = time.perf_counter() - start
    metrics = temporal_metrics(
        source_video_path=input_path,
        stylized_video_path=output_path,
        max_metric_frames=max(1, args.max_metric_frames),
    )
    maybe_save_temporal_plot(
        metrics["series"],
        Path(args.save_plot).expanduser().resolve(strict=False) if args.save_plot else None,
    )

    effective_fps = float(result["frames_processed"] / max(elapsed, 1e-9))
    payload: Dict[str, object] = {
        "mode": "video",
        "device": args.device,
        "input_path": str(input_path),
        "checkpoint_path": str(checkpoint_path),
        "output_path": str(output_path) if args.save_output else None,
        "elapsed_seconds": elapsed,
        "effective_fps": effective_fps,
        "frames_processed": result["frames_processed"],
        "frames_seen": result["frames_seen"],
        "total_frames": result["total_frames"],
        "output_fps": result["fps"],
        "output_resolution": list(result["resolution"]),
        "temporal_pairs_evaluated": metrics["pairs_evaluated"],
        "temporal_warping_error_mae": metrics["temporal_warping_error_mae"],
        "temporal_warping_error_mse": metrics["temporal_warping_error_mse"],
        "naive_frame_diff_mae": metrics["naive_frame_diff_mae"],
    }

    print("\nVideo Evaluation")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Elapsed: {elapsed:.2f}s")
    print(f"Effective FPS: {effective_fps:.2f}")
    print(f"Frames processed: {result['frames_processed']} / {result['frames_seen']}")
    print(f"Temporal warping error (MAE): {payload['temporal_warping_error_mae']}")
    print(f"Temporal warping error (MSE): {payload['temporal_warping_error_mse']}")
    print(f"Naive frame diff (MAE): {payload['naive_frame_diff_mae']}")

    if temp_output_dir is not None:
        temp_output_dir.cleanup()

    return payload


def main() -> None:
    args = parse_args()
    if args.mode == "image":
        metrics = evaluate_image(args)
    else:
        metrics = evaluate_video(args)
    json_out = Path(args.json_out).expanduser().resolve(strict=False) if args.json_out else None
    print_json(metrics, json_out)


if __name__ == "__main__":
    main()
