import logging
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import chat_logger as chat_logger_module


class TestChatLogger(unittest.TestCase):
    def setUp(self):
        self._original_handlers = list(chat_logger_module.logger.handlers)
        self._original_level = chat_logger_module.logger.level
        for handler in list(chat_logger_module.logger.handlers):
            chat_logger_module.logger.removeHandler(handler)
            handler.close()

    def tearDown(self):
        for handler in list(chat_logger_module.logger.handlers):
            chat_logger_module.logger.removeHandler(handler)
            handler.close()
        for handler in self._original_handlers:
            chat_logger_module.logger.addHandler(handler)
        chat_logger_module.logger.setLevel(self._original_level)

    def test_configure_chat_logging_prefers_cli_over_env(self):
        with patch.dict(
            "os.environ",
            {"CHAT_LOG_LEVEL": "ERROR", "LOG_LEVEL": "WARNING"},
            clear=False,
        ):
            chat_logger_module.configure_chat_logging("INFO")

        self.assertEqual(chat_logger_module.logger.level, logging.INFO)

    def test_configure_chat_logging_falls_back_to_chat_log_level_then_log_level(self):
        with patch.dict("os.environ", {"CHAT_LOG_LEVEL": "DEBUG", "LOG_LEVEL": "ERROR"}, clear=False):
            chat_logger_module.configure_chat_logging(None)
        self.assertEqual(chat_logger_module.logger.level, logging.DEBUG)

        with patch.dict("os.environ", {"CHAT_LOG_LEVEL": "", "LOG_LEVEL": "ERROR"}, clear=False):
            chat_logger_module.configure_chat_logging(None)
        self.assertEqual(chat_logger_module.logger.level, logging.ERROR)

    def test_attach_file_handler_is_idempotent_for_same_path(self):
        chat_logger_module.logger.setLevel(logging.INFO)
        root = Path.cwd()

        chat_logger_module.attach_file_handler(root)
        chat_logger_module.attach_file_handler(root)
        chat_logger_module.logger.warning("hello")

        file_handlers = [h for h in chat_logger_module.logger.handlers if isinstance(h, logging.FileHandler)]
        self.assertEqual(len(file_handlers), 1)
        self.assertEqual(Path(file_handlers[0].baseFilename), root / "logs" / "latest.log")

        for handler in file_handlers:
            handler.flush()
        self.assertTrue((root / "logs" / "latest.log").exists())
