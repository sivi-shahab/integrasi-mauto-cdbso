# Fix §9.1 & §9.2: connection pool, multi-worker & batas total koneksi

| Item | Nilai |
|------|-------|
| Isu | [README k6 §9.1](../../../tests/k6/README.md#91-connection-pool-database-kemungkinan-besar-menjadi-bottleneck) pool DB default, [§9.2](../../../tests/k6/README.md#92-jumlah-koneksi-ke-postgresql) total koneksi PostgreSQL |
| Commit fix | `b807940` |
| Hasil | 4 worker: throughput stress **70,25 → 120,46 req/s** (×4,2 dari before 28,55), p95 **3,9 → 1,4 dtk**, p99 lolos threshold; koneksi DB maks **40** (= budget konfigurasi); **0,27% error koneksi (EOF) pada ≥ 175 VU**, penyebab belum dipastikan (§5.4) |
| Bukti before | [BASELINE-ISSUES.md §9.1/§9.2](BASELINE-ISSUES.md#91-connection-pool-db-default--tc-22), [STRESS-BEFORE.md](STRESS-BEFORE.md), [FIX-9.4.md](FIX-9.4.md) (after 9.4) |
| Test case | TC-22, TC-23, **TC-29**, **TC-30** (baru). Semua gate; tidak ada lagi `@known_issue` |

## 1. Kondisi before

- `create_engine(DATABASE_URL)` tanpa konfigurasi: `pool_size=5`, `max_overflow=10`, `pool_timeout=30`,
  `pool_pre_ping=False`, `pool_recycle=-1`. Tidak bisa diatur tanpa mengubah kode (TC-22, TC-23 gagal).
- Service hanya bisa 1 proses lewat `python main.py`, dengan host dan port di-hard-code. CPU 1 core jenuh, sementara
  server punya 8 core (STRESS-BEFORE §5, FIX-9.4 §6).
- Belum ada pengaman total koneksi. PostgreSQL UAT: `max_connections=500`, 142 koneksi aktif saat capture
  (dipakai service lain).
- Koneksi service tidak bisa dibedakan dari service lain di `pg_stat_activity`.

## 2. Perubahan

| File | Perubahan |
|------|-----------|
| `app/core/configs.py` | Setting baru: `APP_HOST`, `APP_PORT`, `APP_WORKERS` (default 1), `DB_POOL_SIZE` (5), `DB_MAX_OVERFLOW` (5), `DB_POOL_TIMEOUT` (10), `DB_POOL_RECYCLE` (1800), `DB_CONNECTION_BUDGET` (100) |
| `app/db/session.py` | `pool_settings()` dari env + `pool_pre_ping=True`; `connect_args={"application_name": "report-mauto-cdsbo"}`; `check_connection_budget(workers)` |
| `main.py` | Sebelum start: cek budget (gagal start jika melebihi), log konfigurasi pool, `uvicorn.run(..., workers=APP_WORKERS)` |
| `app/core/logging.py` | `DailyFileHandler`: file log bertanggal, aman multi-worker (§4) |
| `.env.sample`, `README.md` | Dokumentasi variabel baru & query pemantauan |
| `tests/functional/...` | TC-22/TC-23 menjadi gate; TC-29 & TC-30 baru; TC-25 menerima subclass `TimedRotatingFileHandler` |

### Alasan nilai default

| Setting | Before | After | Alasan |
|---------|--------|-------|--------|
| `pool_size` + `max_overflow` | 5 + 10 | 5 + 5 | Satu worker paling banyak menjalankan ±10 query bersamaan sebelum CPU jenuh. Dengan multi-worker, total koneksi lebih penting daripada koneksi per worker |
| `pool_timeout` | 30 dtk | 10 dtk | Fail fast: lebih baik `responseCode 99` dalam 10 dtk daripada request menggantung 30 dtk |
| `pool_pre_ping` | off | on | Koneksi yang diputus firewall/DB terdeteksi sebelum dipakai (biaya 1 round-trip ringan per checkout) |
| `pool_recycle` | ∞ | 1800 dtk | Koneksi lama dibuat ulang sebelum diputus oleh idle-timeout jaringan |
| `APP_WORKERS` | 1 (hard-code) | env, default **1** | Default tidak mengubah perilaku deploy lama. Nilai produksi diputuskan infra (lihat §6) |
| `DB_CONNECTION_BUDGET` | – | 100 | Konservatif: ±28% dari sisa ±358 koneksi UAT. Perlu persetujuan DBA |

### Perhitungan total koneksi

`total = APP_WORKERS × (DB_POOL_SIZE + DB_MAX_OVERFLOW)`

| `APP_WORKERS` | Total koneksi maks | Budget 100 |
|--------------:|-------------------:|------------|
| 1 | 10 | ✓ |
| 4 | 40 | ✓ (dipakai di stress test) |
| 8 | 80 | ✓ |
| 10 | 100 | ✓ (batas) |
| 20 | 200 | ✗ service gagal start (TC-29) |

Contoh pesan saat ditolak (`APP_WORKERS=20`):

```
ValueError: Total koneksi DB 200 (APP_WORKERS=20 x (DB_POOL_SIZE=5 + DB_MAX_OVERFLOW=5)) melebihi DB_CONNECTION_BUDGET=100
```

Pengecekan budget hanya berlaku saat start lewat `python main.py`. Bila service dijalankan dengan
`uvicorn --workers N` langsung, konfigurasi pool tetap dari env, tetapi budget tidak dicek (didokumentasikan di README).

## 3. Test case & bukti before/after

Diuji terhadap tiga versi kode: original (`146601d`), setelah fix §9.3 (`ebf109f`), dan fix ini (`b807940`).

| TC | Pemeriksaan | `146601d` | `ebf109f` | `b807940` |
|----|-------------|-----------|-----------|-----------|
| TC-22 | `pool_pre_ping` aktif, `pool_timeout` ≤ 10 | ✗ `pre_ping=false`, `timeout=30` | ✗ sama | ✓ `pre_ping=true`, `timeout=10`, `recycle=1800` |
| TC-23 | `DB_POOL_SIZE=3`, `DB_MAX_OVERFLOW=2` dari env | ✗ tetap 5/10 | ✗ tetap 5/10 | ✓ 3/2 |
| TC-29 (baru) | 4 worker diterima (40), 20 worker ditolak (200 > 100) | ✗ fungsi tidak ada | ✗ fungsi tidak ada | ✓ |
| TC-30 (baru) | 2 worker rotasi tengah malam: tidak ada log hilang & semua pindah ke file hari baru | ✗* | ✗ worker ke-2 tetap menulis ke file kemarin | ✓ |

\* Kode original memakai `RotatingFileHandler` berbasis ukuran (bukan harian). Rollover paksa menghasilkan
`detailed_<tanggal>.log.1/.2`, jadi tidak ada file "hari baru" (lihat juga TC-25).

Suite lengkap di setup CI (Postgres + data sintetis) dengan kode baru: **46 passed**, 0 known issue.
Koneksi terlihat di Postgres sebagai `report-mauto-cdsbo`.

Verifikasi `python main.py`:
- `APP_WORKERS=20` → `ValueError ... melebihi DB_CONNECTION_BUDGET=100`, exit code 1, service tidak start.
- `APP_WORKERS=3` → log `Start 3 worker, pool per worker {...}, total koneksi DB maks 30 (budget 100)`, 3 proses
  worker melayani request (HTTP 200), dan file log harian `detailed-2026-11-03.log` dipakai bersama.

## 4. Dampak ke logging multi-worker

Fix §9.3 memakai `TimedRotatingFileHandler` (`logs/detailed.log` → `detailed.log.YYYY-MM-DD`). Di multi-worker,
setiap proses punya stream sendiri ke file yang sama. Saat tengah malam:

1. Worker 1 me-rename `detailed.log` menjadi `detailed.log.2026-11-03` lalu membuka `detailed.log` baru.
2. Worker 2 melihat `detailed.log.2026-11-03` sudah ada. Python 3.13 menganggapnya "already rolled over" dan
   **tidak membuka ulang stream**, sehingga worker 2 terus menulis ke file kemarin.

Bukti (TC-30 pada `ebf109f`): setelah rotasi, log hari baru dari worker 2 tercatat di `detailed.log.2026-11-03`
(`hari2: 1`), bukan di `detailed.log`. Di versi Python lama, langkah 2 bahkan menghapus file hasil rename
worker 1 (log hari sebelumnya hilang).

`DailyFileHandler` menulis langsung ke `logs/<prefix>-YYYY-MM-DD.log` (mode append, tanpa rename). Saat ganti hari,
setiap worker cukup membuka file tanggal baru, dan file di luar `LOG_RETENTION_DAYS` dihapus (aman bila sudah dihapus
worker lain). TC-30 pada `b807940`: kedua worker menulis hari 1 ke `detailed-2026-11-03.log` dan hari 2 ke
`detailed-2026-11-04.log`.

**Nama file log berubah lagi:** `logs/detailed.log` (fix §9.3 awal) → `logs/detailed-YYYY-MM-DD.log`.

## 5. Stress test: before → after 9.4 → after 9.1/9.2

### 5.1 Konfigurasi

Sama dengan [STRESS-BEFORE.md §2](STRESS-BEFORE.md#2-lingkungan--konfigurasi) (server, DB UAT, `tests/k6/data.csv`,
skenario `stress` 20 → 300 VU, k6 0.54.0 Docker di mesin yang sama, `--out csv`). Bedanya, service dijalankan
seperti deploy: `APP_WORKERS=4 APP_PORT=8915 python main.py` (access log uvicorn aktif), commit `b807940`,
2026-11-03 18:20:02 – 18:31:06 WIB.

Resource dicatat tiap 5 detik untuk master + 4 worker: CPU% **instan** (delta `/proc`, berbeda dari kolom CPU
di run sebelumnya yang memakai rata-rata `ps`), RSS total, dan koneksi di `pg_stat_activity` dengan
`application_name='report-mauto-cdsbo'`.

### 5.2 Hasil keseluruhan

| Metrik | Before (`146601d`) | After 9.4 (`813e869`) | After 9.1/9.2 (`b807940`, 4 worker) |
|--------|-------------------:|----------------------:|-----------------------------------:|
| Total request (11 menit) | 18.849 | 46.372 | **79.512** |
| **Throughput** | 28,55 req/s | 70,25 req/s | **120,46 req/s** (×4,2 dari before) |
| Latency p50 | 3.338 ms | 1.436 ms | **417 ms** |
| **Latency p95** | 9.602 ms | 3.913 ms | **1.413 ms** |
| Latency p99 | 10.213 ms | 4.291 ms | **1.949 ms** |
| Latency max | 11.921 ms | 5.275 ms | 3.734 ms |
| Error HTTP | 0% | 0% | **0,27%** (213 request, status 0: `EOF` 185, `connection reset by peer` 28) |
| `responseCode 00` dari response yang diterima | 100% | 100% | 100% (tidak ada code `99`/pool timeout) |
| Data diterima | 63,3 GB (98 MB/s) | 155,1 GB (241 MB/s) | 267,0 GB (**414 MB/s**) |
| CPU service (median beban) | ±1,1 core | ±1,2 core | **±2,3 core** (maks 2,54) dari 4 worker |
| RSS service maks | 1.991 MB | 1.919 MB | **5.352 MB** (4 worker) |
| Koneksi DB service | maks 15 (tidak terukur) | maks 15 (tidak terukur) | median 27, **maks 40**, aktif bersamaan maks 9 |

| Threshold | Before | After 9.4 | After 9.1/9.2 |
|-----------|--------|-----------|---------------|
| `http_req_failed` < 1% (TC-17) | ✓ | ✓ | ✓ 0,27% |
| p95 < 1000 ms (TC-18) | ✗ | ✗ | ✗ 1.413 ms |
| p99 < 2000 ms (TC-19) | ✗ | ✗ | **✓ 1.949 ms** |
| `business_success` > 99% (TC-20) | ✓ | ✓ | ✓ 99,73% |
| `checks` > 99% (TC-21) | ✓ | ✓ | ✓ 99,73% |

### 5.3 Per tahap VU

| Tahap | VU | Before (req/s · p95) | After 9.4 | After 9.1/9.2 | Error 9.1/9.2 |
|-------|---:|---------------------:|----------:|--------------:|--------------:|
| 0 → 20 | 19 | 24,5 · 758 ms | 56,8 · 270 ms | **76,7 · 179 ms** | 0 |
| 20 → 50 | 49 | 28,6 · 1.687 ms | 69,8 · 726 ms | **116,9 · 404 ms** | 0 |
| 50 → 100 | 99 | 29,9 · 3.402 ms | 69,5 · 1.503 ms | **125,5 · 696 ms** | 0 |
| 100 → 200 | 199 | 28,9 · 7.017 ms | 73,0 · 2.676 ms | **125,6 · 1.155 ms** | 5 (0,03%) |
| 200 → 300 | 299 | 28,9 · 9.878 ms | 72,7 · 4.132 ms | **130,5 · 1.768 ms** | 141 (0,90%) |
| 300 → 0 | 300 | 28,6 · 10.187 ms | 73,0 · 4.220 ms | **125,8 · 1.614 ms** | 67 (0,44%) |

Per 30 detik: [`k6_stress_after_fix912_timeline.csv`](k6_stress_after_fix912_timeline.csv) (dengan kolom `failed`).

**Kapasitas yang memenuhi p95 < 1 dtk:** before ±20 VU → after 9.4 ±55 VU → **after 9.1/9.2 ±145 VU**
(p95 862 ms pada 124 VU, 1.014 ms pada 149 VU), dengan throughput ±125 req/s. Service pulih penuh setelah beban
turun (43 ms pada 1 VU).

### 5.4 Error koneksi (EOF) pada VU tinggi: belum terselesaikan

- 213 request (0,27%) gagal **tanpa response HTTP**: `EOF` (185) dan `read: connection reset by peer` (28). Error
  pertama muncul di ±175 VU (detik 360), lalu memuncak 47–58 per 30 detik pada 274–300 VU. Durasi request yang gagal
  24–1.278 ms, jadi ini **bukan timeout**.
- **Yang sudah dikesampingkan:**
  - Tidak ada worker yang mati/restart (log uvicorn hanya start dan shutdown normal, jumlah proses tetap 6).
  - Tidak ada error/exception di log aplikasi, dan tidak ada `responseCode 99` (pool DB tidak timeout).
  - Koneksi DB tidak melewati batas (maks 40, aktif bersamaan maks 9).
- **Uji lanjutan 90 detik, 250 VU konstan, 4 worker, tanpa `--out csv`:**

  | Konfigurasi | Request | Throughput | p95 | Error |
  |-------------|--------:|-----------:|----:|------:|
  | `uvicorn --workers 4 --timeout-keep-alive 5 --no-access-log` | 16.687 | 182,7 req/s | 2,03 s | **0** |
  | `uvicorn --workers 4 --timeout-keep-alive 30 --no-access-log` | 17.262 | 188,6 req/s | 1,98 s | **0** |
  | `APP_WORKERS=4 python main.py` (access log aktif, sama dengan stress test) | 17.179 | 188,2 req/s | 1,94 s | **0** |

  Error tidak bisa direproduksi, dan setting keep-alive maupun access log tidak berpengaruh.
- **Dugaan (belum terbukti):** k6, raw output CSV (±1 juta baris), 4 worker, dan proses lain di server bersama
  (termasuk proses `code` yang terus memakai ±2 core) berebut CPU selama 11 menit pada 300 koneksi. Throughput
  stress (125–130 req/s di plateau) lebih rendah dari uji 90 detik (±185 req/s), yang menandakan ada pembatas di luar
  service. CPU service sendiri hanya ±2,3 dari 4 core.
- **Tindak lanjut:** ulangi stress test dengan k6 di **mesin terpisah** (README k6 §4) dan pantau `ss -s` /
  `netstat` di server saat VU tinggi. Hingga itu dilakukan, anggap batas aman **±150 VU konkuren** untuk 4 worker.

### 5.5 Dampak ke infrastruktur

- **Database & jaringan:** 414 MB/s data diterima k6 berarti service juga menarik volume yang sama dari DB UAT
  lewat jaringan (±3,3 Gbit/s). Ini konsekuensi kontrak response tetap (§9.4). Wajib diinformasikan ke DBA/infra
  sebelum `APP_WORKERS` dinaikkan di produksi.
- **Memori:** 4 worker mencapai 5,35 GB RSS total pada 300 VU (±1,3 GB per worker). Server punya 62 GB, cukup,
  tetapi naik linear terhadap jumlah worker.
- **Koneksi DB:** maks 40 = `APP_WORKERS × (DB_POOL_SIZE + DB_MAX_OVERFLOW)`, sesuai perhitungan. Hanya ±9 yang aktif
  bersamaan; sisanya idle di pool.

## 6. Rekomendasi konfigurasi produksi

| Setting | Rekomendasi awal | Catatan |
|---------|------------------|---------|
| `APP_WORKERS` | 4 | Terbukti di test ini. Lebih dari 4 di server bersama perlu diuji ulang (k6 terpisah) |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | 5 / 5 | Aktif bersamaan hanya ±9 dari 40. Bisa diturunkan ke 3/3 bila budget ketat |
| `DB_CONNECTION_BUDGET` | 100 | **Perlu persetujuan DBA** (sisa ±358 dari 500 di UAT; cek nilai produksi) |
| `DB_POOL_TIMEOUT` | 10 | – |
| `LOG_LEVEL` | INFO | – |

Keputusan jumlah worker dan budget koneksi ada di tim infra/DBA. Default kode tetap `APP_WORKERS=1` agar deploy
lama tidak berubah tanpa disengaja.

## 7. Keterbatasan

- k6 berjalan di mesin yang sama dengan service. Server dipakai proses lain (§5.4).
- Satu kali run stress per tahap. Variasi antar run belum diukur.
- Data uji 10 kombinasi. CPU/IO server database tidak diukur.
- CPU% run ini instan (delta `/proc`), sedangkan run before/after 9.4 memakai rata-rata `ps`. Bandingkan trennya, bukan angka mutlaknya.

## 8. File

| File | Isi |
|------|-----|
| [`k6_stress_after_fix912.txt`](k6_stress_after_fix912.txt) | Ringkasan k6 |
| [`k6_stress_after_fix912_timeline.csv`](k6_stress_after_fix912_timeline.csv) | RPS, latency, error per 30 detik |
| [`resource_stress_after_fix912.csv`](resource_stress_after_fix912.csv) | CPU instan, RSS, jumlah proses, koneksi DB (total/aktif/idle) per 5 detik |
| `tests/k6/published/after-fix-9.1-9.2/summary_stress_20261103_113103.{json,txt}` | Allure TS-07 `stress · Internal UAT · after fix 9.1 9.2` |
