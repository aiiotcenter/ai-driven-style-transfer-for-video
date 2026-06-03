import json
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, override_settings

from style_transfer.views import webcam_video_view


class WebcamVideoViewDispatchTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _build_request(self):
        upload = SimpleUploadedFile(
            "webcam-recording.webm",
            b"fake-video-bytes",
            content_type="video/webm",
        )
        return self.factory.post(
            "/style_transfer/webcam-video/",
            {"style": "starry-night", "video": upload},
        )

    @override_settings(DEBUG=True, WEBCAM_VIDEO_TASK_MODE="thread")
    @patch("style_transfer.views.default_storage.save", return_value="temp/mock.webm")
    @patch("style_transfer.views.resolve_style_model", return_value=("/tmp/model.pth", "starry-night"))
    @patch("style_transfer.views.set_job_state")
    @patch("style_transfer.views.process_webcam_video.delay")
    @patch("style_transfer.views.Thread")
    def test_thread_mode_starts_local_background_job(
        self,
        thread_cls,
        delay_mock,
        set_job_state_mock,
        resolve_style_model_mock,
        save_mock,
    ):
        thread_instance = MagicMock()
        thread_cls.return_value = thread_instance

        response = webcam_video_view(self._build_request())
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["execution_mode"], "thread")
        delay_mock.assert_not_called()
        thread_cls.assert_called_once()
        thread_instance.start.assert_called_once()
        set_job_state_mock.assert_called_once()
        resolve_style_model_mock.assert_called_once()
        save_mock.assert_called_once()

    @override_settings(DEBUG=True, WEBCAM_VIDEO_TASK_MODE="celery")
    @patch("style_transfer.views.default_storage.save", return_value="temp/mock.webm")
    @patch("style_transfer.views.resolve_style_model", return_value=("/tmp/model.pth", "starry-night"))
    @patch("style_transfer.views.set_job_state")
    @patch("style_transfer.views.process_webcam_video.delay")
    @patch("style_transfer.views.Thread")
    def test_celery_mode_queues_task(
        self,
        thread_cls,
        delay_mock,
        set_job_state_mock,
        resolve_style_model_mock,
        save_mock,
    ):
        response = webcam_video_view(self._build_request())
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["execution_mode"], "celery")
        delay_mock.assert_called_once()
        thread_cls.assert_not_called()
        set_job_state_mock.assert_called_once()
        resolve_style_model_mock.assert_called_once()
        save_mock.assert_called_once()
