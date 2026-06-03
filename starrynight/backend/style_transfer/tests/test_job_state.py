import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from style_transfer.job_state import get_job_state, set_job_state, update_job_state


class JobStateFallbackTests(SimpleTestCase):
    def test_set_job_state_writes_file_when_cache_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(BASE_DIR=Path(temp_dir)):
                with patch("style_transfer.job_state.cache.set", side_effect=RuntimeError("redis down")):
                    set_job_state("abc123", {"status": "queued", "progress": 0})

                saved = get_job_state("abc123")

        self.assertEqual(saved["status"], "queued")
        self.assertEqual(saved["progress"], 0)

    def test_update_job_state_merges_with_existing_file_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(BASE_DIR=Path(temp_dir)):
                with patch("style_transfer.job_state.cache.set", side_effect=RuntimeError("redis down")):
                    set_job_state("abc123", {"status": "queued", "progress": 0})
                    update_job_state("abc123", status="processing", progress=25)

                saved = get_job_state("abc123")

        self.assertEqual(saved["status"], "processing")
        self.assertEqual(saved["progress"], 25)
