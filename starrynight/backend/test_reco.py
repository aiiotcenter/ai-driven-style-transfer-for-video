import os
import tempfile

import cv2
import numpy as np
import torch

from style_transfer.reco.network import ReCoNet
from style_transfer.reco.reco_infer import stylize_video


def create_tiny_input_video(path: str, frames: int = 8, fps: float = 8.0) -> None:
    writer = cv2.VideoWriter(
        path,
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (320, 240),
    )
    if not writer.isOpened():
        raise RuntimeError(f"Could not create test video at {path}")

    for i in range(frames):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:, :, 0] = (i * 25) % 255
        frame[:, :, 1] = 120
        frame[:, :, 2] = 255 - ((i * 25) % 255)
        cv2.putText(
            frame,
            f"frame-{i}",
            (30, 120),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        writer.write(frame)
    writer.release()


if __name__ == "__main__":
    tmpdir = tempfile.mkdtemp(prefix="reco_test_")
    input_video = os.path.join(tmpdir, "input.mp4")
    output_video = os.path.join(tmpdir, "output.mp4")

    create_tiny_input_video(input_video)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ReCoNet().to(device).eval()
    result = stylize_video(input_video, output_video, model)

    if not os.path.exists(output_video):
        raise RuntimeError("Output video was not created")

    cap = cv2.VideoCapture(output_video)
    output_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if output_frames <= 0:
        raise RuntimeError("Output video has zero frames")

    print("test_reco.py PASS")
    print(result)

