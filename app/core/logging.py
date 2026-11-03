"""Konfigurasi logging aplikasi.

Perbaikan README k6 §9.3:
- File log dirotasi harian (TimedRotatingFileHandler, tengah malam):
  logs/detailed.log -> logs/detailed.log.YYYY-MM-DD, disimpan LOG_RETENTION_DAYS hari.
- Level log diatur lewat env LOG_LEVEL (default INFO), sehingga log per request
  (DEBUG) tidak ditulis saat beban tinggi.
- Semua output log menyamarkan NIK (16 digit) termasuk traceback, sebagai
  lapisan pengaman jika ada pesan/exception yang memuat NIK.

Env (opsional): LOG_LEVEL (default INFO), LOG_DIR (default logs), LOG_RETENTION_DAYS (default 30).
"""
import logging
import logging.handlers
import os
import re
from pathlib import Path

_NIK = re.compile(r"(?<!\d)(\d{4})\d{8}(\d{4})(?!\d)")


def mask_nik(text: str) -> str:
    """3201133107990002 -> 3201********0002 (angka 16 digit berdiri sendiri)."""
    return _NIK.sub(r"\1********\2", text)


class MaskingFormatter(logging.Formatter):
    """Formatter yang menyamarkan NIK pada pesan dan traceback."""

    def format(self, record: logging.LogRecord) -> str:
        return mask_nik(super().format(record))


def setup_logging():
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    retention = int(os.getenv("LOG_RETENTION_DAYS", "30"))

    detailed_formatter = MaskingFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    simple_formatter = MaskingFormatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(simple_formatter)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / "detailed.log", when="midnight", backupCount=retention, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(detailed_formatter)

    error_file_handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / "error.log", when="midnight", backupCount=retention, encoding="utf-8"
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(detailed_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_file_handler)

    return root_logger
