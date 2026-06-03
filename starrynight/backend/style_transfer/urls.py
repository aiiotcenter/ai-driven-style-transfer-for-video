from django.urls import path

from . import views

urlpatterns = [
    path("models/", views.get_models, name="models"),
    path("webcam-styles/", views.webcam_styles_view, name="webcam-styles"),
    path("style/", views.stylize_image_view, name="style"),
    path("video/", views.stylize_video_view, name="video"),
    path("webcam-video/", views.webcam_video_view, name="webcam-video"),
    path("video-status/<str:job_id>/", views.video_status_view, name="video-status"),
]
