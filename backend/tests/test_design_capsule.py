import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURE_URL = Path(__file__).resolve().parent.joinpath("fixtures", "design_fixture.html").as_uri()
MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".mp4", ".webm", ".woff", ".woff2", ".ttf", ".otf"}

sys.path.insert(0, str(BACKEND_DIR))

import app as app_module
from design_capsule import create_design_capsule_zip
from env_config import load_env_file
from gemini_design import GeminiDesignError, extract_json_object


class FakeThread:
    def __init__(self, target=None, args=()):
        self.target = target
        self.args = args
        self.daemon = False

    def start(self):
        return None


class AppModeApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="kopiiki-api-test-")
        self.original_paths = {
            "DOWNLOAD_FOLDER": app_module.DOWNLOAD_FOLDER,
            "EXTRACTED_FOLDER": app_module.EXTRACTED_FOLDER,
            "JOBS_FOLDER": app_module.JOBS_FOLDER,
            "TEMP_DOWNLOAD_FOLDER": app_module.TEMP_DOWNLOAD_FOLDER,
            "HISTORY_FILE": app_module.HISTORY_FILE,
        }
        app_module.DOWNLOAD_FOLDER = os.path.join(self.temp_dir, "downloads")
        app_module.EXTRACTED_FOLDER = os.path.join(self.temp_dir, "extracted_sites")
        app_module.JOBS_FOLDER = os.path.join(app_module.EXTRACTED_FOLDER, "jobs")
        app_module.TEMP_DOWNLOAD_FOLDER = os.path.join(app_module.DOWNLOAD_FOLDER, ".tmp")
        app_module.HISTORY_FILE = os.path.join(app_module.DOWNLOAD_FOLDER, "history.json")
        os.makedirs(app_module.DOWNLOAD_FOLDER, exist_ok=True)
        os.makedirs(app_module.JOBS_FOLDER, exist_ok=True)
        os.makedirs(app_module.TEMP_DOWNLOAD_FOLDER, exist_ok=True)
        app_module.EXTRACTION_JOBS.clear()
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module.EXTRACTION_JOBS.clear()
        for name, value in self.original_paths.items():
            setattr(app_module, name, value)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_old_extract_request_defaults_to_snapshot_mode(self):
        with patch.object(app_module, "PLAYWRIGHT_AVAILABLE", True), patch.object(app_module, "validate_target_url", return_value=None), patch.object(app_module.threading, "Thread", FakeThread):
            response = self.client.post("/api/extract", json={"url": "https://example.com/"})

        self.assertEqual(response.status_code, 200)
        extract_id = response.get_json()["extract_id"]
        job = app_module.EXTRACTION_JOBS[extract_id]
        self.assertEqual(job["mode"], "snapshot")
        self.assertTrue(job["filename"].endswith(".zip"))
        self.assertNotIn("-design", job["filename"])

    def test_design_mode_without_key_returns_clear_error(self):
        with patch.object(app_module, "PLAYWRIGHT_AVAILABLE", True), patch.object(app_module, "validate_target_url", return_value=None), patch.dict(os.environ, {"GEMINI_API_KEY": "", "KOPIIKI_GEMINI_MOCK": ""}):
            response = self.client.post("/api/extract", json={"url": "https://example.com/", "mode": "design"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("GEMINI_API_KEY", response.get_json()["error"])
        self.assertEqual(app_module.EXTRACTION_JOBS, {})

    def test_invalid_mode_returns_400(self):
        with patch.object(app_module, "PLAYWRIGHT_AVAILABLE", True):
            response = self.client.post("/api/extract", json={"url": "https://example.com/", "mode": "poster"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("snapshot", response.get_json()["error"])

    def test_private_targets_are_blocked_by_default(self):
        with patch.object(app_module, "PLAYWRIGHT_AVAILABLE", True), patch.object(app_module, "PRIVATE_TARGETS_ALLOWED", False):
            response = self.client.post("/api/extract", json={"url": "http://127.0.0.1:5176/", "mode": "snapshot"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("blocked", response.get_json()["error"])
        self.assertEqual(app_module.EXTRACTION_JOBS, {})

    def test_non_http_urls_are_rejected(self):
        with patch.object(app_module, "PLAYWRIGHT_AVAILABLE", True):
            response = self.client.post("/api/extract", json={"url": "file:///tmp/site.html", "mode": "snapshot"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("http", response.get_json()["error"])

    def test_config_endpoint_reports_design_ai_without_exposing_key(self):
        with patch.dict(os.environ, {"KOPIIKI_GEMINI_MOCK": "1", "GEMINI_API_KEY": "secret-test-key"}):
            response = self.client.get("/api/config")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["design_ai"]["configured"])
        self.assertTrue(data["design_ai"]["mock"])
        self.assertNotIn("secret-test-key", json.dumps(data))


class EnvConfigTests(unittest.TestCase):
    def test_load_env_file_sets_missing_values_without_overriding_existing_env(self):
        temp_dir = tempfile.mkdtemp(prefix="kopiiki-env-test-")
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        env_path = Path(temp_dir) / ".env"
        env_path.write_text(
            "\n".join(
                [
                    "GEMINI_API_KEY=from-file",
                    "KOPIIKI_GEMINI_MODEL='gemini-test-model'",
                    "BAD KEY=ignored",
                ]
            ),
            encoding="utf-8",
        )

        with patch.dict(os.environ, {"GEMINI_API_KEY": "existing"}, clear=False):
            os.environ.pop("KOPIIKI_GEMINI_MODEL", None)
            loaded = load_env_file(env_path)
            self.assertTrue(loaded)
            self.assertEqual(os.environ["GEMINI_API_KEY"], "existing")
            self.assertEqual(os.environ["KOPIIKI_GEMINI_MODEL"], "gemini-test-model")


class DesignCapsuleZipTests(unittest.TestCase):
    def test_invalid_gemini_json_raises_readable_error(self):
        with self.assertRaises(GeminiDesignError) as error:
            extract_json_object("not json")
        self.assertIn("invalid JSON", str(error.exception))

    def test_mock_design_capsule_zip_structure_and_asset_prompt_fields(self):
        zip_path = self._create_capsule_with_env({"KOPIIKI_GEMINI_MOCK": "1"})
        self._assert_capsule_zip(zip_path)

    @unittest.skipUnless(os.environ.get("GEMINI_API_KEY"), "GEMINI_API_KEY is not set; skipping real Gemini smoke test.")
    def test_real_gemini_smoke_when_key_is_available(self):
        env = {"KOPIIKI_GEMINI_MOCK": ""}
        zip_path = self._create_capsule_with_env(env)
        self._assert_capsule_zip(zip_path)

    def _create_capsule_with_env(self, env):
        temp_dir = tempfile.mkdtemp(prefix="kopiiki-capsule-test-")
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        output_dir = os.path.join(temp_dir, "out")
        temp_zip_path = os.path.join(temp_dir, "fixture-design.tmp.zip")
        with patch.dict(os.environ, env, clear=False):
            try:
                zip_path, _metadata = create_design_capsule_zip(
                    url=FIXTURE_URL,
                    output_dir=output_dir,
                    extract_id="test-design-capsule",
                    temp_zip_path=temp_zip_path,
                )
            except Exception as exc:
                if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
                    self.skipTest(f"Playwright Chromium is not installed: {exc}")
                raise
        return zip_path

    def _assert_capsule_zip(self, zip_path):
        required = {
            "DESIGN.md",
            "design/references/section-anatomy.md",
            "design/references/layout-grammar.md",
            "design/references/font-strategy.md",
            "design/references/component-families.md",
            "design/references/motion.md",
            "design/references/responsive.md",
            "design/references/asset-prompts.md",
            "design/references/visual-checkpoints.md",
            "design/evidence/observations.md",
            "design/evidence/section-map.md",
            "design/evidence/observations.json",
            "design/scripts/validate-design-capsule.mjs",
        }
        with zipfile.ZipFile(zip_path) as archive:
            names = set(archive.namelist())
            self.assertTrue(required.issubset(names))
            media_files = [name for name in names if Path(name).suffix.lower() in MEDIA_EXTENSIONS]
            self.assertEqual(media_files, [])

            design_md = archive.read("DESIGN.md").decode("utf-8")
            self.assertIn("## Transfer Boundary", design_md)
            self.assertIn("## Font Strategy", design_md)
            self.assertIn("## Visual Checkpoints", design_md)
            self.assertIn("Do not preserve proprietary pixels", design_md)

            font_strategy = archive.read("design/references/font-strategy.md").decode("utf-8")
            self.assertIn("Do not copy or bundle source commercial font files", font_strategy)

            section_anatomy = archive.read("design/references/section-anatomy.md").decode("utf-8")
            self.assertIn("Evidence ID:", section_anatomy)
            self.assertIn("### Stable Dimensions", section_anatomy)
            self.assertIn("### Layer Map", section_anatomy)

            observations = json.loads(archive.read("design/evidence/observations.json").decode("utf-8"))
            for image in observations.get("image_inputs", []):
                self.assertNotIn("data", image)
                self.assertIn("byte_length", image)

            prompts = archive.read("design/references/asset-prompts.md").decode("utf-8")
            blocks = [block for block in prompts.split("## Asset Prompt:")[1:] if block.strip()]
            self.assertGreaterEqual(len(blocks), 5)
            for block in blocks:
                for field in ["Role:", "Format:", "Size:", "Aspect ratio:", "Background:", "Alpha:", "Placement:", "Prompt:", "Avoid:", "Notes:"]:
                    self.assertIn(field, block)

            checkpoints = archive.read("design/references/visual-checkpoints.md").decode("utf-8")
            self.assertIn("Visual Checkpoints", checkpoints)


if __name__ == "__main__":
    unittest.main(verbosity=2)
