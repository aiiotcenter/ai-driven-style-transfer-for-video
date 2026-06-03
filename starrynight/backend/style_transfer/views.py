from pathlib import Path
import base64
import io
import tempfile
import uuid
from threading import Thread

import cv2
from PIL import Image
from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .apps import StyleTransferConfig
from .fast_style.api import stlye_transfer
from .job_state import get_job_state, set_job_state
from .reco.model_utils import preferred_reconet_model_path, resolve_existing_reconet_model
from .reco.style_catalog import available_styles, resolve_style_model
from .reco.reco_infer import stylize_video
from .tasks import process_webcam_video

MAX_UPLOAD_BYTES = 100 * 1024 * 1024


def _webcam_task_mode() -> str:
    configured = str(getattr(settings, "WEBCAM_VIDEO_TASK_MODE", "")).strip().lower()
    if configured in {"celery", "thread"}:
        return configured
    return "thread" if settings.DEBUG else "celery"


def _dispatch_webcam_job(job_id: str, temp_path: str, selected_style: str) -> str:
    if _webcam_task_mode() == "celery":
        process_webcam_video.delay(job_id, temp_path, selected_style)
        return "celery"

    Thread(
        target=process_webcam_video.run,
        args=(job_id, temp_path, selected_style),
        daemon=True,
    ).start()
    return "thread"


@api_view(["GET"])
def get_models(request):
    return Response(StyleTransferConfig.refresh_model_paths())


@api_view(["GET"])
def webcam_styles_view(request):
    styles, default_style = available_styles(Path(settings.BASE_DIR))
    return Response({"default_style": default_style, "styles": styles})


@api_view(["POST"])
def stylize_image_view(request):
    image = request.FILES.get("image")
    models_raw = request.data.get("style")
    if image is None:
        return Response({"error": "No image uploaded"}, status=400)
    if models_raw is None:
        return Response({"error": "No style selected"}, status=400)

    model_paths = [model.strip() for model in str(Path(models_raw)).split(",") if model.strip()]
    styled_images = {}

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
        for chunk in image.chunks():
            temp_file.write(chunk)
        temp_file.file.seek(0)
        img = cv2.imread(temp_file.name)
        if img is None:
            return Response({"error": "Could not decode image"}, status=400)

        img = cv2.resize(img, (400, 300), interpolation=cv2.INTER_AREA)
        for model_path in model_paths:
            loaded_model = StyleTransferConfig.get_loaded_model(model_path)
            if loaded_model is None:
                return Response({"error": f"Model not found: {model_path}"}, status=400)

            styled_image = stlye_transfer(model=loaded_model, content=img)
            styled_image = cv2.cvtColor(styled_image, cv2.COLOR_BGR2RGB)
            styled_image = Image.fromarray(styled_image.astype("uint8"))

            file_object = io.BytesIO()
            styled_image.save(file_object, "PNG")
            file_object.seek(0)
            styled_images[model_path] = base64.b64encode(file_object.read()).decode("utf-8")

    return Response(styled_images)


@csrf_exempt
def stylize_video_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    video_file = request.FILES.get("video")
    if not video_file:
        return JsonResponse({"error": "No video uploaded"}, status=400)

    try:
        input_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        output_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")

        for chunk in video_file.chunks():
            input_temp.write(chunk)
        input_temp.close()
        output_temp.close()

        model_path = resolve_existing_reconet_model(Path(settings.BASE_DIR))
        if not model_path:
            expected_path = preferred_reconet_model_path(Path(settings.BASE_DIR))
            return JsonResponse(
                {
                    "error": (
                        "ReCoNet checkpoint is missing. "
                        f"Expected file at: {expected_path}"
                    )
                },
                status=500,
            )
        stylize_video(input_temp.name, output_temp.name, model_path)

        return FileResponse(open(output_temp.name, "rb"), content_type="video/mp4")
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@csrf_exempt
def webcam_video_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    video_file = request.FILES.get("video")
    if not video_file:
        return JsonResponse({"error": "No video"}, status=400)

    if not (getattr(video_file, "content_type", "") or "").startswith("video/"):
        return JsonResponse({"error": "Invalid upload type. Please upload a video file."}, status=400)

    if getattr(video_file, "size", 0) > MAX_UPLOAD_BYTES:
        return JsonResponse({"error": "File too large (max 100MB)"}, status=400)

    selected_style = request.POST.get("style")
    try:
        _, selected_style = resolve_style_model(Path(settings.BASE_DIR), selected_style)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except FileNotFoundError as exc:
        return JsonResponse({"error": str(exc)}, status=500)

    job_id = str(uuid.uuid4())
    suffix = Path(video_file.name or "webcam.mp4").suffix or ".mp4"
    temp_path = default_storage.save(f"temp/{job_id}{suffix}", video_file)

    set_job_state(
        job_id,
        {
            "status": "queued",
            "progress": 0,
            "video_url": None,
            "error": None,
            "style": selected_style,
        },
    )

    try:
        execution_mode = _dispatch_webcam_job(job_id, temp_path, selected_style)
    except Exception:
        # If Celery or the broker is unavailable, keep local development usable.
        Thread(
            target=process_webcam_video.run,
            args=(job_id, temp_path, selected_style),
            daemon=True,
        ).start()
        execution_mode = "thread"
    return JsonResponse(
        {
            "job_id": job_id,
            "status": "queued",
            "style": selected_style,
            "execution_mode": execution_mode,
            "message": "Video queued for processing",
        }
    )


def video_status_view(request, job_id):
    if request.method != "GET":
        return JsonResponse({"error": "GET only"}, status=405)

    job_data = get_job_state(job_id)
    if not job_data:
        return JsonResponse({"error": "Job not found"}, status=404)

    return JsonResponse(
        {
            "status": job_data.get("status", "queued"),
            "progress": job_data.get("progress", 0),
            "video_url": job_data.get("video_url"),
            "error": job_data.get("error"),
            "style": job_data.get("style"),
        }
    )
