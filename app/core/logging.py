"""Konfigurasi logging aplikasi.

Perbaikan README k6 §9.3:
- File log harian: logs/detailed-YYYY-MM-DD.log dan logs/error-YYYY-MM-DD.log, berganti
  tengah malam, disimpan LOG_RETENTION_DAYS hari. Aman untuk beberapa worker
  (APP_WORKERS > 1): file tidak di-rename, setiap proses hanya append ke file
  tanggal berjalan (lihat DailyFileHandler).
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
import time
from datetime import date, datetime, timedelta
from pathlib import Path

_NIK = re.compile(r"(?<!\d)(\d{4})\d{8}(\d{4})(?!\d)")


def mask_nik(text: str) -> str:
    """3201133107990002 -> 3201********0002 (angka 16 digit berdiri sendiri)."""
    return _NIK.sub(r"\1********\2", text)


class MaskingFormatter(logging.Formatter):
    """Formatter yang menyamarkan NIK pada pesan dan traceback."""

    def format(self, record: logging.LogRecord) -> str:
        return mask_nik(super().format(record))


class DailyFileHandler(logging.handlers.TimedRotatingFileHandler):
    """Rotasi harian yang aman untuk multi-proses.

    TimedRotatingFileHandler standar me-rename file saat tengah malam; bila beberapa
    worker menulis file yang sama, worker berikutnya menghapus hasil rename worker
    pertama (log hari sebelumnya hilang). Handler ini menulis langsung ke file
    bertanggal (<prefix>-YYYY-MM-DD.log) dalam mode append, sehingga saat ganti hari
    tiap proses cukup membuka file tanggal baru tanpa rename.
    """

    def __init__(self, directory: Path, prefix: str, backupCount: int = 30, encoding: str = "utf-8"):
        self.directory = Path(directory)
        self.prefix = prefix
        super().__init__(self._path_for(date.today()), when="midnight",
                         backupCount=backupCount, encoding=encoding)

    def _path_for(self, day: date) -> str:
        return str(self.directory / f"{self.prefix}-{day.isoformat()}.log")

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        self.baseFilename = os.path.abspath(self._path_for(date.today()))
        self.stream = self._open()
        self.rolloverAt = self.computeRollover(int(time.time()))
        self._remove_expired()

    def _remove_expired(self):
        if self.backupCount <= 0:
            return
        oldest = date.today() - timedelta(days=self.backupCount)
        for f in self.directory.glob(f"{self.prefix}-*.log"):
            try:
                day = datetime.strptime(f.stem[len(self.prefix) + 1:], "%Y-%m-%d").date()
            except ValueError:
                continue
            if day < oldest:
                try:
                    f.unlink()
                except FileNotFoundError:  # sudah dihapus worker lain
                    pass


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

    file_handler = DailyFileHandler(log_dir, "detailed", backupCount=retention)
    file_handler.setLevel(level)
    file_handler.setFormatter(detailed_formatter)

    error_file_handler = DailyFileHandler(log_dir, "error", backupCount=retention)
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(detailed_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_file_handler)

    return root_logger
