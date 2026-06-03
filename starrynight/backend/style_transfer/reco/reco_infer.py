from __future__ import annotations

from collections import OrderedDict
from math import ceil
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional, Tuple, Union

import cv2
import torch
from torch import nn

from .network import ReCoNet

DEFAULT_FPS = 24.0
DEFAULT_FRAME_SIZE: Tuple[int, int] = (640, 360)


def _build_reconet_torch_key_map() -> Dict[str, str]:
    key_map: Dict[str, str] = {}
    for i, name in enumerate(("conv1", "conv2", "conv3"), start=1):
        key_map[f"cir{i}.conv.weight"] = f"{name}.conv2d.weight"
        key_map[f"cir{i}.conv.bias"] = f"{name}.conv2d.bias"
        key_map[f"cir{i}.inst.weight"] = f"{name}.instance.weight"
        key_map[f"cir{i}.inst.bias"] = f"{name}.instance.bias"

    for i in range(1, 6):
        key_map[f"rir{i}.conv1.weight"] = f"res{i}.conv1.conv2d.weight"
        key_map[f"rir{i}.conv1.bias"] = f"res{i}.conv1.conv2d.bias"
        key_map[f"rir{i}.inst1.weight"] = f"res{i}.in1.weight"
        key_map[f"rir{i}.inst1.bias"] = f"res{i}.in1.bias"
        key_map[f"rir{i}.conv2.weight"] = f"res{i}.conv2.conv2d.weight"
        key_map[f"rir{i}.conv2.bias"] = f"res{i}.conv2.conv2d.bias"
        key_map[f"rir{i}.inst2.weight"] = f"res{i}.in2.weight"
        key_map[f"rir{i}.inst2.bias"] = f"res{i}.in2.bias"

    for i, name in enumerate(("deconv1", "deconv2"), start=1):
        key_map[f"devcir{i}.conv.weight"] = f"{name}.conv2d.weight"
        key_map[f"devcir{i}.conv.bias"] = f"{name}.conv2d.bias"
        key_map[f"devcir{i}.inst.weight"] = f"{name}.instance.weight"
        key_map[f"devcir{i}.inst.bias"] = f"{name}.instance.bias"

    key_map["tanh.conv.weight"] = "deconv3.conv2d.weight"
    key_map["tanh.conv.bias"] = "deconv3.conv2d.bias"
    return key_map


RECONET_TORCH_KEY_MAP = _build_reconet_torch_key_map()


def _model_device(model: nn.Module) -> torch.device:
    try:
        return next(model.parameters()).device
    except StopIteration:
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _extract_state_dict(raw_obj: object) -> Mapping[str, torch.Tensor]:
    if isinstance(raw_obj, Mapping):
        for candidate in ("state_dict", "model_state_dict", "model"):
            nested = raw_obj.get(candidate)
            if isinstance(nested, Mapping):
                raw_obj = nested
                break

    if not isinstance(raw_obj, Mapping):
        raise ValueError("Checkpoint must contain a state_dict mapping.")

    state_dict: Dict[str, torch.Tensor] = {}
    for name, value in raw_obj.items():
        if isinstance(value, torch.Tensor):
            cleaned_name = str(name)
            if cleaned_name.startswith("module."):
                cleaned_name = cleaned_name[len("module.") :]
            state_dict[cleaned_name] = value

    if not state_dict:
        raise ValueError("Checkpoint did not contain tensor parameters.")
    return state_dict


def _normalize_state_dict(state_dict: Mapping[str, torch.Tensor]) -> Mapping[str, torch.Tensor]:
    if "conv1.conv2d.weight" in state_dict and "deconv3.conv2d.weight" in state_dict:
        return state_dict

    if "cir1.conv.weight" in state_dict and "tanh.conv.weight" in state_dict:
        missing = [src for src in RECONET_TORCH_KEY_MAP if src not in state_dict]
        if missing:
            missing_list = ", ".join(missing[:5])
            raise ValueError(
                "ReCoNet checkpoint is missing expected parameters "
                f"(first missing: {missing_list})."
            )

        remapped = OrderedDict()
        for src_name, dst_name in RECONET_TORCH_KEY_MAP.items():
            remapped[dst_name] = state_dict[src_name]
        return remapped

    sample_keys = ", ".join(list(state_dict.keys())[:6])
    raise ValueError(
        "Unsupported ReCoNet checkpoint format. "
        f"Example keys: {sample_keys}"
    )


def _load_weights_into_model(model: nn.Module, state_dict: Mapping[str, torch.Tensor]) -> None:
    target_state = model.state_dict()
    loaded_keys = 0
    for name, tensor in state_dict.items():
        target = target_state.get(name)
        if target is None:
            continue
        if target.shape != tensor.shape:
            raise ValueError(
                f"Checkpoint tensor shape mismatch for {name}: "
                f"expected {tuple(target.shape)}, got {tuple(tensor.shape)}."
            )
        target.copy_(tensor)
        loaded_keys += 1

    if loaded_keys == 0:
        raise ValueError("No compatible parameters were loaded from checkpoint.")


def load_model(model_path: Union[str, Path], device: Union[str, torch.device, None] = None) -> nn.Module:
    target_device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    model_path = Path(model_path)
    if not model_path.exists():
        raise FileNotFoundError(f"ReCoNet checkpoint not found: {model_path}")

    net = ReCoNet().to(target_device)
    raw_state = torch.load(str(model_path), map_location=target_device)
    state_dict = _extract_state_dict(raw_state)
    state_dict = _normalize_state_dict(state_dict)
    _load_weights_into_model(net, state_dict)
    net.eval()
    return net


def _open_video_capture(input_path: str) -> cv2.VideoCapture:
    capture = cv2.VideoCapture(input_path)
    if capture.isOpened():
        return capture
    capture.release()
    raise ValueError(
        "Unable to open input video. "
        "Use a browser-recorded WebM/MP4 file with supported codecs."
    )


def _open_video_writer(
    output_path: str,
    fps: float,
    frame_size: Tuple[int, int],
) -> cv2.VideoWriter:
    for fourcc_text in ("avc1", "mp4v", "MJPG"):
        fourcc = cv2.VideoWriter_fourcc(*fourcc_text)
        writer = cv2.VideoWriter(output_path, fourcc, fps, frame_size)
        if writer.isOpened():
            return writer
        writer.release()
    raise ValueError(f"Unable to open output video writer: {output_path}")


def stylize_video(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    model: Union[str, Path, nn.Module],
    progress_callback: Optional[Callable[[int, int], None]] = None,
    target_fps: Optional[float] = None,
) -> Dict[str, Union[str, int, float, Tuple[int, int]]]:
    """
    Stream stylization for videos.
    - Keeps memory bounded by processing one frame at a time.
    - Enforces 640x360 inference resolution.
    - Loads weights only once (if model is a path).
    """
    input_path = str(input_path)
    output_path = str(output_path)

    if isinstance(model, (str, Path)):
        net = load_model(model)
    else:
        net = model
        net.eval()

    device = _model_device(net)

    capture = _open_video_capture(input_path)

    fps = capture.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = DEFAULT_FPS
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    sample_stride = 1
    output_fps = float(fps)
    if target_fps and target_fps > 0 and fps > target_fps:
        sample_stride = max(1, int(ceil(fps / target_fps)))
        output_fps = max(1.0, float(fps) / sample_stride)

    width, height = DEFAULT_FRAME_SIZE
    writer = _open_video_writer(output_path, output_fps, (width, height))

    frames_processed = 0
    frames_seen = 0
    try:
        with torch.no_grad():
            while True:
                ok, frame_bgr = capture.read()
                if not ok:
                    break
                frames_seen += 1

                if sample_stride > 1 and (frames_seen - 1) % sample_stride != 0:
                    if progress_callback is not None:
                        progress_callback(frames_seen, total_frames)
                    continue

                resized_bgr = cv2.resize(frame_bgr, (width, height), interpolation=cv2.INTER_AREA)
                frame_rgb = cv2.cvtColor(resized_bgr, cv2.COLOR_BGR2RGB)

                frame_tensor = (
                    torch.from_numpy(frame_rgb)
                    .permute(2, 0, 1)
                    .float()
                    .unsqueeze(0)
                    .to(device)
                )

                try:
                    _, styled_tensor = net(frame_tensor)
                except RuntimeError as exc:
                    if "out of memory" in str(exc).lower():
                        raise RuntimeError("GPU out of memory while stylizing video.") from exc
                    raise
                styled_rgb = (
                    styled_tensor[0]
                    .detach()
                    .clamp(0, 255)
                    .permute(1, 2, 0)
                    .to(torch.uint8)
                    .cpu()
                    .numpy()
                )

                styled_bgr = cv2.cvtColor(styled_rgb, cv2.COLOR_RGB2BGR)
                writer.write(styled_bgr)
                frames_processed += 1
                if progress_callback is not None:
                    progress_callback(frames_seen, total_frames)
    finally:
        capture.release()
        writer.release()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    return {
        "output_path": output_path,
        "frames_processed": frames_processed,
        "frames_seen": frames_seen,
        "total_frames": total_frames,
        "fps": float(output_fps),
        "resolution": (width, height),
    }
