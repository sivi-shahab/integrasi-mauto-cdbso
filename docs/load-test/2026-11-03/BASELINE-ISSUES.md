# Baseline Isu README k6 §9 — sebelum perbaikan

Tanggal capture: 2026-11-03 · Commit: `f49252e` (main) · Rencana perbaikan: [`docs/implementation-fixing-plan.md`](../../implementation-fixing-plan.md)

Dokumen ini adalah **bukti "before"**: kondisi service sebelum isu di
[`tests/k6/README.md` §9](../../../tests/k6/README.md#9-risiko--hal-yang-perlu-diperhatikan) diperbaiki.
Setelah perbaikan, isi bagian [After](#after-setelah-perbaikan) dengan cara capture yang sama.

Bukti tersedia di tiga tempat:

| Bukti | Before (sekarang) | After (setelah fix) |
|-------|-------------------|---------------------|
| Allure TS-08 (TC-22 – TC-27) | 6 test case **gagal** | test case lulus, tab *History* menunjukkan gagal → lulus |
| Allure TS-07 k6 internal (load & stress) | `Internal UAT · before fix` (`tests/k6/published/before/`) | `Internal UAT · after fix` (`tests/k6/published/after/`) |
| Dokumen ini | bagian Before | bagian After |

Report: <https://sivi-shahab.github.io/integrasi-mauto-cdbso/>

## Before (sebelum perbaikan)

### §9.1 Connection pool DB default — TC-22

Konfigurasi engine yang dipakai service (`app/db/session.py`, dibaca dari objek `engine.pool`):

```json
{"class": "QueuePool", "pool_size": 5, "max_overflow": 10, "timeout": 30.0, "pre_ping": false, "recycle": -1}
```

- Maksimal 15 koneksi per worker; request yang menunggu pool > 30 detik → `responseCode 99` dengan HTTP 200.
- `pool_pre_ping=false`: koneksi yang diputus DB/firewall baru ketahuan saat dipakai (request gagal).
- Hasil TC-22: `AssertionError: pool_pre_ping=False: koneksi mati tidak dideteksi sebelum dipakai`.

### §9.2 Total koneksi PostgreSQL — TC-23

- Ukuran pool tidak bisa diatur tanpa ubah kode. Hasil TC-23 (env `DB_POOL_SIZE=3`):
  `AssertionError: pool_size=5, diharapkan 3 dari env DB_POOL_SIZE (belum bisa dikonfigurasi)`.
- PostgreSQL UAT: `max_connections = 500`, koneksi aktif saat capture **142** (dipakai service lain).
- Service saat ini 1 worker → maks 15 koneksi. Rencana multi-worker (P2) harus dihitung terhadap sisa ±358 koneksi.

### §9.3 Log aplikasi — TC-24, TC-25

- Setiap request sukses menulis 1 baris `INFO` berisi **NIK lengkap** (contoh, NIK disamarkan):
  ```
  2026-11-03 11:17:01,429 - app.service.report_mauto_service - INFO - [report_mauto_service.py:102] - report_mauto nik=3201********0002 apply_date=2025-09-29 rows=10
  ```
  `logs/detailed_2026-10-01.log`: 1.180 baris INFO, **1.162** di antaranya memuat NIK.
- **Rotasi tidak berjalan harian:** file `logs/detailed_2026-10-01.log` (nama = tanggal service start)
  terakhir ditulis **2026-11-03**, jadi log selama ±1 bulan masuk satu file. Handler: `RotatingFileHandler`
  (rotasi berdasarkan ukuran 10 MB, bukan tanggal).
- Hasil TC-24: `1 baris log INFO memuat NIK`. Hasil TC-25: `File log tidak dirotasi harian: RotatingFileHandler (detailed_<tanggal>.log), RotatingFileHandler (error_<tanggal>.log)`.

### §9.4 Ukuran response — TC-26, TC-27

Ukuran kolom di tabel `public.report_mauto_cdsbo` UAT (295 baris, 151 MB):

| Kolom | Rata-rata / baris | Maks / baris |
|-------|-------------------|--------------|
| `request_base64_ktp` | 375,2 KB | 1.250,9 KB |
| `profile_pic` | 131,1 KB | — |
| `selfie` | 49,7 KB | 196,8 KB |
| **Seluruh baris (JSON)** | **563,0 KB** | **1.426,1 KB** |
| Seluruh baris tanpa 3 kolom gambar | ±7 KB | — |

- ±99% ukuran response berasal dari 3 kolom gambar base64. Catatan: `profile_pic` belum disebut di README k6 §9.4.
- Hasil TC-26 (CI, data dummy berukuran sama): `Response masih memuat kolom gambar: {'selfie': 600.0, 'request_base64_ktp': 4500.0, 'profile_pic': 1572.0} (KB)`.
- Hasil TC-27 (CI): `rata-rata 561.3 KB per baris (response 6736 KB untuk 12 baris)`.

### k6 load test internal (TS-07, `Internal UAT · before fix`)

Sumber: `tests/k6/published/before/summary_load_20261103_043349.json`. Skenario `load` (20 VU, 5 menit),
1 proses uvicorn, server 8 core, DB UAT, 10 kombinasi data uji.

| Metrik | Nilai |
|--------|-------|
| Throughput | **26,54 req/s** |
| Latency avg / p95 / p99 / max | 568 / **997,6** / 1.218 / 1.968 ms |
| Error HTTP / business | 0% / 0% |
| Data diterima | 26,97 GB (**92 MB/s**, ±3,4 MB per response) |
| Threshold | semua lulus, p95 hanya 2,4 ms di bawah batas 1000 ms |

Perbandingan di CI (k6 `smoke`, 1 VU, data dummy): data kecil ±100 req/s → data berukuran UAT **21 req/s**,
menunjukkan ukuran response adalah faktor dominan.

### k6 stress test internal (TS-07, `Internal UAT · before fix`)

Laporan lengkap: [STRESS-BEFORE.md](STRESS-BEFORE.md). Sumber: `tests/k6/published/before/summary_stress_20261103_094255.json`.
Skenario `stress` (20 → 300 VU, 11 menit), konfigurasi sama dengan load test.

| Metrik | Nilai |
|--------|-------|
| Throughput | **28,55 req/s**, flat dari 20 sampai 300 VU (jenuh sejak ±20 VU) |
| Latency p95 / p99 / max | **9.602 / 10.213** / 11.921 ms; p95 > 1 dtk mulai ±27 VU |
| Error HTTP / business | 0% / 0% (tidak ada code `99`) |
| Data diterima | 63,3 GB (98,2 MB/s, 3,6 MB/response) |
| CPU / RAM service | ±110% (±1,1 core) / maks 1.991 MB |
| Threshold | **GAGAL**: p95 < 1000 ms (TC-18) dan p99 < 2000 ms (TC-19) |

## After (setelah perbaikan)

Status per 2026-11-03: **§9.3 dan §9.4 selesai**, §9.1/§9.2 belum. Detail: [FIX-9.4.md](FIX-9.4.md), [FIX-9.3.md](FIX-9.3.md).

Langkah untuk isu berikutnya:

1. Hapus tag `@known_issue` dari skenario yang sudah diperbaiki di `tests/functional/features/report_mauto.feature`.
2. Push → pastikan TC terkait **lulus** di Allure; catat nomor run GitHub Actions di tabel bawah.
3. Jalankan k6 dengan skenario & konfigurasi yang sama dengan before, simpan ke `tests/k6/published/after/`.
4. Ulangi capture di dokumen ini (konfigurasi pool, contoh log, ukuran response) dan isi tabel:

| Isu | TC | Before | After | Run / commit after |
|-----|----|--------|-------|--------------------|
| §9.1 | TC-22 | gagal (`pre_ping=false`, `timeout=30`) | | |
| §9.2 | TC-23 | gagal (pool tidak bisa diatur) | | |
| §9.3 | TC-24 | gagal (NIK di log INFO) | ✅ lulus: 0 baris log memuat NIK lengkap | fix §9.3 ([FIX-9.3.md](FIX-9.3.md)) |
| §9.3 | TC-25 | gagal (`RotatingFileHandler`) | ✅ lulus: `TimedRotatingFileHandler` midnight | fix §9.3 |
| §9.3 | TC-28 (baru) | gagal (kode lama: NIK lengkap 6× di error/traceback) | ✅ lulus: 0×, tersamar 6× | fix §9.3 |
| §9.4 | TC-26 | gagal (definisi awal: 3 kolom gambar di response) | ✅ lulus: diganti guard kontrak (kolom gambar **tetap**, keputusan 2026-11-03) | `813e869` ([FIX-9.4.md](FIX-9.4.md)) |
| §9.4 | TC-27 | gagal (definisi awal: 561 KB/baris; definisi baru: render 52–56 ms) | ✅ lulus: render ±17 ms (< 35 ms) | `813e869` |
| k6 load | TS-07 | 26,5 req/s, p95 997,6 ms | *belum dijalankan ulang* | |
| k6 stress | TS-07 | 28,6 req/s, p95 9.602 ms, RAM 2 GB, 0% error ([STRESS-BEFORE.md](STRESS-BEFORE.md)) | **70,3 req/s (×2,46)**, p95 3.913 ms, RAM 1,9 GB, 0% error; threshold p95/p99 masih gagal di 300 VU | `813e869` (fix §9.4) |
