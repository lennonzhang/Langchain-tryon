import os
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.settings import env_loader


class TestEnvLoader(unittest.TestCase):
    def setUp(self):
        env_loader._LOADED_ENV_ROOTS.clear()

    def tearDown(self):
        env_loader._LOADED_ENV_ROOTS.clear()
        os.environ.pop("LOADER_TEST_KEY", None)

    def test_load_env_file_reads_each_root_once(self):
        root = Path("D:/fake-root")
        with (
            patch("backend.settings.env_loader.Path.exists", return_value=True),
            patch("backend.settings.env_loader.Path.is_file", return_value=True),
            patch("backend.settings.env_loader.Path.read_text", return_value="LOADER_TEST_KEY=first") as read_mock,
        ):
            env_loader.load_env_file(root)
            env_loader.load_env_file(root)
        self.assertEqual(os.environ["LOADER_TEST_KEY"], "first")
        read_mock.assert_called_once()
