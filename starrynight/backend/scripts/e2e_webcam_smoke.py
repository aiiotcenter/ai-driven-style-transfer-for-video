from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Tuple
from urllib.parse import urljoin

import cv2
import numpy as np
import requests


def create_test_video(path: Path, frames: int = 20, fps: float = 10.0, size: Tuple[int, int] = (320, 240)) -> None:
    width, height = size
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Could not open test video writer: {path}")
    for i in range(frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :, 0] = (i * 17) % 255
        frame[:, :, 1] = 120
        frame[:, :, 2] = 255 - ((i * 17) % 255)
        cv2.putText(frame, f"smoke-{i}", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        writer.write(frame)
    writer.release()


def verify_playable(path: Path) -> int:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Output video is not readable: {path}")
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    capture.release()
    if frame_count <= 0:
        raise RuntimeError("Output video contains zero frames")
    return frame_count


def run_smoke(base_url: str, timeout_seconds: int) -> None:
    with tempfile.TemporaryDirectory(prefix="webcam_smoke_") as temp_dir:
        temp_dir_path = Path(temp_dir)
        input_video = temp_dir_path / "input.mp4"
        output_video = temp_dir_path / "output.mp4"

        create_test_video(input_video)
        styles_response = requests.get(urljoin(base_url, "/style_transfer/webcam-styles/"), timeout=20)
        styles_response.raise_for_status()
        styles_payload = styles_response.json()
        default_style = styles_payload.get("default_style")
        available_styles = [item for item in styles_payload.get("styles", []) if item.get("available")]
        if not available_styles:
            raise RuntimeError("No available webcam styles returned by API")
        selected_style = default_style if any(s["id"] == default_style for s in available_styles) else available_styles[0]["id"]
        print(f"Using style: {selected_style}", flush=True)

        upload_start = time.perf_counter()
        with input_video.open("rb") as handle:
            response = requests.post(
                urljoin(base_url, "/style_transfer/webcam-video/"),
                data={"style": selected_style},
                files={"video": ("smoke.mp4", handle, "video/mp4")},
                timeout=30,
            )
        upload_elapsed = time.perf_counter() - upload_start
        response.raise_for_status()
        payload = response.json()
        job_id = payload.get("job_id")
        if not job_id:
            raise RuntimeError(f"Upload did not return job_id. Payload: {json.dumps(payload)}")

        print(f"Queued job_id={job_id} in {upload_elapsed:.2f}s", flush=True)

        poll_start = time.perf_counter()
        status_payload = {}
        queued_streak = 0
        while True:
            if time.perf_counter() - poll_start > timeout_seconds:
                raise TimeoutError(f"Timed out waiting for completion after {timeout_seconds}s")

            status_response = requests.get(
                urljoin(base_url, f"/style_transfer/video-status/{job_id}/"),
                timeout=20,
            )
            status_response.raise_for_status()
            status_payload = status_response.json()
            status = status_payload.get("status")
            progress = status_payload.get("progress", 0)
            print(f"Status={status} progress={progress}%", flush=True)

            if status == "queued":
                queued_streak += 1
            else:
                queued_streak = 0
            if queued_streak >= 20:
                raise RuntimeError(
                    "Job remained queued for too long. "
                    "Check Redis cache sharing between Django and Celery."
                )

            if status == "completed":
                break
            if status == "failed":
                raise RuntimeError(status_payload.get("error") or "Processing failed")
            time.sleep(2)

        processing_elapsed = time.perf_counter() - poll_start
        video_url = status_payload.get("video_url")
        if not video_url:
            raise RuntimeError("Completed job did not provide video_url")
        full_video_url = urljoin(base_url, video_url)

        download_start = time.perf_counter()
        output_response = requests.get(full_video_url, timeout=120)
        output_response.raise_for_status()
        output_video.write_bytes(output_response.content)
        download_elapsed = time.perf_counter() - download_start

        output_frames = verify_playable(output_video)
        print(f"Output playable: {output_video} ({output_frames} frames)", flush=True)
        print(f"Processing time: {processing_elapsed:.2f}s", flush=True)
        print(f"Download time: {download_elapsed:.2f}s", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="End-to-end webcam processing smoke test.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Django server base URL")
    parser.add_argument("--timeout", type=int, default=300, help="Max wait time for processing completion")
    args = parser.parse_args()
    run_smoke(args.base_url, timeout_seconds=args.timeout)


if __name__ == "__main__":
    main()
