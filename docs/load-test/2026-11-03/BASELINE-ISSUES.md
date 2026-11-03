# Baseline Isu README k6 §9 — sebelum perbaikan

Tanggal capture: 2026-11-03 · Commit: `f49252e` (main) · Rencana perbaikan: [`docs/implementation-fixing-plan.md`](../../implementation-fixing-plan.md)

Dokumen ini adalah **bukti "before"**: kondisi service sebelum isu di
[`tests/k6/README.md` §9](../../../tests/k6/README.md#9-risiko--hal-yang-perlu-diperhatikan) diperbaiki.
Setelah perbaikan, isi bagian [After](#after-setelah-perbaikan) dengan cara capture yang sama.

Bukti tersedia di tiga tempat:

| Bukti | Before (sekarang) | After (setelah fix) |
|-------|-------------------|---------------------|
| Allure TS-08 (TC-22 – TC-27) | 6 test case **gagal** | test case lulus, tab *History* menunjukkan gagal → lulus |
| Allure TS-07 k6 internal | `Internal UAT · before fix` (`tests/k6/published/before/`) | `Internal UAT · after fix` (`tests/k6/published/after/`) |
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

> Stress test (`SCENARIO=stress`) sebelum fix belum dijalankan. Jalankan di server internal dan simpan ke
> `tests/k6/published/before/` **sebelum** mulai perbaikan agar ada pembanding (lihat README k6 §13).

## After (setelah perbaikan)

*Belum diisi.* Setelah perbaikan:

1. Hapus tag `@known_issue` dari skenario yang sudah diperbaiki di `tests/functional/features/report_mauto.feature`.
2. Push → pastikan TC terkait **lulus** di Allure; catat nomor run GitHub Actions di tabel bawah.
3. Jalankan k6 dengan skenario & konfigurasi yang sama dengan before, simpan ke `tests/k6/published/after/`.
4. Ulangi capture di dokumen ini (konfigurasi pool, contoh log, ukuran response) dan isi tabel:

| Isu | TC | Before | After | Run / commit after |
|-----|----|--------|-------|--------------------|
| §9.1 | TC-22 | gagal (`pre_ping=false`, `timeout=30`) | | |
| §9.2 | TC-23 | gagal (pool tidak bisa diatur) | | |
| §9.3 | TC-24 | gagal (NIK di log INFO) | | |
| §9.3 | TC-25 | gagal (`RotatingFileHandler`) | | |
| §9.4 | TC-26 | gagal (3 kolom gambar di response) | | |
| §9.4 | TC-27 | gagal (561 KB/baris) | | |
| k6 load | TS-07 | 26,5 req/s, p95 997,6 ms | | |
| k6 stress | TS-07 | *belum dijalankan* | | |
