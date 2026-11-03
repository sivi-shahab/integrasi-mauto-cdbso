# Fix §9.3: logging (NIK di log & rotasi harian)

| Item | Nilai |
|------|-------|
| Isu | [README k6 §9.3](../../../tests/k6/README.md#93-log-aplikasi): log `INFO` per request memuat NIK, file log tidak dirotasi harian |
| Hasil | NIK lengkap di log: **1.162 baris → 0**, rotasi **harian**, log per request tidak ditulis pada `LOG_LEVEL=INFO` |
| Bukti before | [BASELINE-ISSUES.md §9.3](BASELINE-ISSUES.md#93-log-aplikasi--tc-24-tc-25) |
| Test case | TC-24, TC-25, **TC-28 (baru)**. Semuanya gate (tanpa `@known_issue`) |

## 1. Kondisi before

- `report_mauto_service.py` menulis `logger.info("report_mauto nik=%s ...")` di **setiap** request sukses.
  `logs/detailed_2026-10-01.log` berisi 1.162 baris INFO yang memuat NIK lengkap.
- `logger.exception("... params=%s", params)` mencatat dict parameter yang berisi `nik`. Pesan error SQLAlchemy
  juga ikut menampilkan `[parameters: {...}]`, termasuk NIK.
- `RotatingFileHandler` dengan nama file berisi tanggal **saat service start** (`detailed_<tanggal>.log`), rotasi per
  10 MB. File `detailed_2026-10-01.log` masih ditulis pada 2026-11-03, artinya ±1 bulan log masuk satu file.
- Level log root di-hard-code `DEBUG` dan tidak bisa diatur.

## 2. Perubahan (berlapis)

| Lapisan | File | Perubahan |
|---------|------|-----------|
| 1. Sumber | `app/service/report_mauto_service.py` | Log per request diturunkan ke **DEBUG** dan **tanpa NIK** (`apply_date`, `rows`, `query_ms`). Log error mencatat parameter **tanpa** `nik` |
| 2. Database | `app/db/session.py` | `create_engine(..., hide_parameters=True)`: pesan error SQLAlchemy tidak memuat nilai parameter query |
| 3. Formatter | `app/core/logging.py` | `MaskingFormatter`: semua output log (console, file, **traceback**) menyamarkan angka 16 digit → `3201********0002`. Berlaku juga untuk v2/liveness |
| 4. Rotasi | `app/core/logging.py` | `TimedRotatingFileHandler(when="midnight")`: `logs/detailed.log`, `logs/error.log` → `*.log.YYYY-MM-DD`, disimpan `LOG_RETENTION_DAYS` hari |
| 5. Level | `app/core/logging.py`, `.env.sample` | Env `LOG_LEVEL` (default `INFO`), `LOG_DIR` (default `logs`), `LOG_RETENTION_DAYS` (default 30) |

Untuk troubleshooting, set `LOG_LEVEL=DEBUG`. Log per request akan muncul lagi, tanpa NIK.

Lapisan 3 adalah jaring pengaman. Angka lain yang kebetulan 16 digit (misalnya nomor kartu) juga ikut tersamar.
Itu disengaja, karena itu juga data sensitif.

## 3. Test case & bukti before/after

| TC | Skenario | Kode lama | Kode baru |
|----|----------|-----------|-----------|
| TC-24 | Request ke service, baris log baru level INFO tidak memuat NIK. Ditambah langkah baru: **tidak ada NIK lengkap di level apa pun** | **gagal**: 1 baris INFO memuat NIK per request | **lulus**: 0 baris |
| TC-25 | Handler file = `TimedRotatingFileHandler`, `when=MIDNIGHT` | **gagal**: `RotatingFileHandler (detailed_2026-11-03.log)` | **lulus** |
| TC-28 (baru) | `logger.exception` + `logger.error` dengan NIK di pesan dan traceback, lalu periksa isi file log | **gagal**: NIK lengkap 6×, tersamar 0× | **lulus**: NIK lengkap 0×, tersamar 6× |

Suite lengkap di setup CI (Postgres + data sintetis) dengan kode baru:
- `pytest -m "not known_issue"`: **42 passed**.
- `pytest -m known_issue`: hanya TC-22 & TC-23 (§9.1/§9.2, belum diperbaiki) yang gagal.
- File log service setelah suite: `logs/detailed.log`, `logs/error.log`. String NIK uji `3201133107990002`
  muncul **0 kali**.

## 4. Verifikasi rotasi

Rollover dipaksa 2× (meniru pergantian tengah malam) dengan `LOG_RETENTION_DAYS=2`:

```
['detailed.log', 'detailed.log.2026-11-01', 'detailed.log.2026-11-02', 'error.log']
```

- File aktif selalu `detailed.log`. File hari sebelumnya diberi akhiran tanggal.
- File di luar retensi dihapus otomatis.
- `log.debug(...)` tidak ditulis pada `LOG_LEVEL=INFO`.

## 5. Dampak & catatan operasional

- **Nama file log berubah:** `logs/detailed_<tanggal>.log` → `logs/detailed.log` (+ `detailed.log.<tanggal>`).
  Sesuaikan monitoring atau pengumpul log yang membaca pola nama lama.
- File log lama (`detailed_*.log`) yang **sudah berisi NIK** tidak dihapus otomatis. Disarankan diarsipkan atau
  dihapus sesuai kebijakan retensi data (koordinasi tim security).
- Volume log turun drastis: di `LOG_LEVEL=INFO` tidak ada lagi 1 baris per request.
- **Multi-worker (P2):** `TimedRotatingFileHandler` tidak aman bila beberapa proses menulis file yang sama
  (rotasi bisa bentrok). Saat P2, gunakan satu file per worker, log ke stdout (dikelola systemd/docker), atau
  `logrotate` dengan `copytruncate`.

## 6. File yang berubah

`app/core/logging.py`, `app/service/report_mauto_service.py`, `app/db/session.py`, `.env.sample`,
`tests/functional/features/report_mauto.feature`, `tests/functional/test_report_mauto.py`.
