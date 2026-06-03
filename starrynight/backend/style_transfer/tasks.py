import os
from typing import Optional

from celery import shared_task
from django.conf import settings
from django.core.files.storage import default_storage

from .apps import StyleTransferConfig
from .fast_style.api import stlye_transfer
from .job_state import update_job_state
from .reco.style_catalog import resolve_style_model

def _update_job(job_id: str, **payload) -> None:
    update_job_state(job_id, **payload)


def _friendly_error(exc: Exception) -> str:
    message = str(exc).strip()
    lowered = message.lower()
    if "out of memory" in lowered:
        return "Processing failed: GPU out of memory."
    if "unable to open input video" in lowered:
        return "Processing failed: unsupported or corrupted video codec."
    if "unable to open output video writer" in lowered:
        return "Processing failed: could not initialize output video encoder."
    return message or "Processing failed due to an unexpected error."


def _process_webcam_video_fast(
    input_abs: str,
    output_abs: str,
    model_path: str,
    progress_callback,
) -> None:
    from math import ceil

    import cv2

    capture = cv2.VideoCapture(input_abs)
    if not capture.isOpened():
        capture.release()
        raise ValueError(
            "Unable to open input video. Use a browser-recorded WebM/MP4 file with supported codecs."
        )

    fps = capture.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 24.0
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    target_fps = 8.0
    sample_stride = max(1, int(ceil(float(fps) / target_fps))) if fps > target_fps else 1
    output_fps = max(1.0, float(fps) / sample_stride)
    frame_size = (640, 360)

    writer = None
    for fourcc_text in ("avc1", "mp4v", "MJPG"):
        candidate = cv2.VideoWriter(
            output_abs,
            cv2.VideoWriter_fourcc(*fourcc_text),
            output_fps,
            frame_size,
        )
        if candidate.isOpened():
            writer = candidate
            break
        candidate.release()

    if writer is None:
        capture.release()
        raise ValueError(f"Unable to open output video writer: {output_abs}")

    model = StyleTransferConfig.get_loaded_model(model_path)

    frames_seen = 0
    try:
        while True:
            ok, frame_bgr = capture.read()
            if not ok:
                break
            frames_seen += 1
            if sample_stride > 1 and (frames_seen - 1) % sample_stride != 0:
                progress_callback(frames_seen, total_frames)
                continue

            resized = cv2.resize(frame_bgr, frame_size, interpolation=cv2.INTER_AREA)
            styled = stlye_transfer(model=model, content=resized).clip(0, 255).astype("uint8")
            writer.write(styled)
            progress_callback(frames_seen, total_frames)
    finally:
        capture.release()
        writer.release()


@shared_task(bind=True, soft_time_limit=60 * 58, time_limit=60 * 60)
def process_webcam_video(self, job_id: str, temp_path: str, style: Optional[str] = None) -> None:
    try:
        model_path, selected_style = resolve_style_model(settings.BASE_DIR, style)
        _update_job(job_id, status="processing", progress=0, error=None, style=selected_style)

        input_abs = default_storage.path(temp_path)
        output_rel = f"output/video-{job_id}.mp4"
        output_abs = default_storage.path(output_rel)
        os.makedirs(os.path.dirname(output_abs), exist_ok=True)

        def on_progress(frames_done: int, total_frames: int) -> None:
            if total_frames > 0:
                progress = min(99, int((frames_done / total_frames) * 100))
            else:
                # Unknown frame count - keep progress indeterminate but moving.
                progress = min(99, frames_done % 100)
            _update_job(job_id, status="processing", progress=progress)

        _process_webcam_video_fast(
            input_abs,
            output_abs,
            model_path,
            progress_callback=on_progress,
        )
        _update_job(
            job_id,
            status="completed",
            progress=100,
            video_url=f"{settings.MEDIA_URL}{output_rel}",
            error=None,
            style=selected_style,
        )
    except Exception as exc:
        _update_job(job_id, status="failed", progress=0, error=_friendly_error(exc))
    finally:
        # Week-1 cleanup can be basic.
        try:
            default_storage.delete(temp_path)
        except Exception:
            pass
