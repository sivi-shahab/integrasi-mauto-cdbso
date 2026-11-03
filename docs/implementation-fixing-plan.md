# Implementation Fixing Plan — `POST /v1/report_mauto`

Tanggal: 2026-11-03 · Sumber temuan: [`tests/k6/README.md` §9](../tests/k6/README.md#9-risiko--hal-yang-perlu-diperhatikan)
dan [`docs/load-test/2026-11-03/REPORT.md`](load-test/2026-11-03/REPORT.md).

## 1. Status temuan §9 README k6

| Poin | Temuan | Status | Kondisi kode saat ini |
|------|--------|--------|-----------------------|
| 9.1 | Connection pool DB default | ❌ Belum | `app/db/session.py` memakai `create_engine(DATABASE_URL)` tanpa konfigurasi: `pool_size=5`, `max_overflow=10`, `pool_timeout=30`, tanpa `pool_pre_ping` |
| 9.2 | Total koneksi ke PostgreSQL | ⚠️ Belum relevan | Masih 1 worker (`main.py`), maks 15 koneksi. Relevan setelah multi-worker |
| 9.3 | Log `INFO` per request | ❌ Belum | `report_mauto_service.py` menulis 1 log `INFO` per request, berisi NIK. Nama file log memakai tanggal saat startup, tidak berganti per hari |
| 9.4 | Ukuran response (`SELECT *`) | ❌ Belum | Masih `SELECT *` termasuk `request_base64_ktp`, `profile_pic`, `selfie` (±563 KB/baris di UAT); rata-rata ~3,4 MB/response, maks 13,5 MB |
| 9.5 | Batas mesin k6 | n/a | Catatan operasional mesin load test, bukan bug aplikasi |

Bukti kondisi sebelum perbaikan: [`docs/load-test/2026-11-03/BASELINE-ISSUES.md`](load-test/2026-11-03/BASELINE-ISSUES.md),
Allure **TS-08** (TC-22 – TC-27, tag `@known_issue`), dan GitHub Issues dari [`docs/issues/`](issues/).

| Isu | Test case Allure | GitHub Issue (template) |
|-----|------------------|-------------------------|
| 9.1 | TC-22 | `docs/issues/9.1-connection-pool.md` |
| 9.2 | TC-23 | `docs/issues/9.2-total-koneksi.md` |
| 9.3 | TC-24, TC-25 | `docs/issues/9.3-logging.md` |
| 9.4 | TC-26, TC-27 | `docs/issues/9.4-ukuran-response.md` |

Fix yang sudah masuk `main`: paging tidak stabil (tiebreaker `ctid`, commit `ddb2345`) dan
functional test BDD + Allure (commit `3abf776`), kini berjalan otomatis di GitHub Actions.

Hasil load test (20 VU): service jenuh di ±26 req/s, bottleneck **CPU 1 proses uvicorn** dan
**serialisasi response besar**. Pool DB belum menjadi bottleneck pada beban ini.

## 2. Rencana perbaikan (urut prioritas)

### P1 — Kurangi ukuran response (9.4) · perlu keputusan bisnis

- **Masalah:** kolom gambar base64 mendominasi ukuran response dan CPU serialisasi JSON.
- **Rencana:**
  1. Konfirmasi ke klien/konsumen API apakah `selfie`, `request_base64_ktp`, dan `profile_pic` dibutuhkan di endpoint list.
  2. Ganti `SELECT *` dengan daftar kolom eksplisit tanpa kolom gambar.
  3. Jika gambar tetap dibutuhkan: endpoint detail terpisah per `application_id`
     (mis. `POST /v1/report_mauto/image`), atau flag opsional `include_images` (default `false`)
     agar kontrak lama tetap bisa dipakai selama masa transisi.
- **File:** `app/service/report_mauto_service.py`, `app/schemas/report_mauto_schema.py`, dokumentasi API.
- **Risiko:** breaking change ke klien → wajib dikomunikasikan / versi baru.
- **Verifikasi:** functional test (TC-02 field utama tetap ada) + k6 `load`: ukuran response dan p95 turun.

### P2 — Multi-worker + konfigurasi pool (9.1 & 9.2)

- **Masalah:** 1 proses Python hanya memakai 1 core dari 8 core server; pool memakai default.
- **Rencana:**
  1. Jalankan beberapa worker: `uvicorn main:app --workers N` (atau gunicorn + `uvicorn.workers.UvicornWorker`).
     Mulai dari `N = 4`.
  2. Konfigurasi pool lewat environment variable agar bisa disesuaikan per environment:
     ```python
     engine = create_engine(
         DATABASE_URL,
         pool_size=settings.DB_POOL_SIZE,          # default 5
         max_overflow=settings.DB_MAX_OVERFLOW,    # default 5
         pool_timeout=settings.DB_POOL_TIMEOUT,    # default 10 detik (fail fast)
         pool_pre_ping=True,                       # hindari koneksi mati
         pool_recycle=1800,
     )
     ```
  3. Hitung batas koneksi: `N worker × (pool_size + max_overflow)` harus < `max_connections`
     PostgreSQL dikurangi koneksi service lain. Contoh 4 × 10 = 40 koneksi. Koordinasi dengan DBA.
  4. Update `.env.sample` dan README dengan variabel baru.
- **File:** `app/db/session.py`, `app/core/configs.py`, `.env.sample`, `main.py` / skrip deploy.
- **Verifikasi:** k6 `load` & `stress` — throughput naik mendekati ×N, `non_success_response_code{code:99}` tetap 0;
  pantau `pg_stat_activity`.

### P3 — Logging (9.3)

- **Masalah:** log per request di level `INFO` berisi NIK (data pribadi) dan membesar cepat saat beban tinggi.
- **Rencana:**
  1. Turunkan log sukses ke `DEBUG`, atau hapus NIK dari pesan log (cukup jumlah baris + durasi).
  2. Ganti `RotatingFileHandler` dengan nama file bertanggal startup menjadi
     `TimedRotatingFileHandler(when="midnight", backupCount=N)` agar rotasi per hari benar.
  3. Level log console/file dibuat bisa diatur dari env (`LOG_LEVEL`).
- **File:** `app/service/report_mauto_service.py`, `app/core/logging.py`.
- **Verifikasi:** jalankan k6 `load`, ukuran folder `logs/` tidak tumbuh signifikan; tidak ada NIK di log `INFO`.

### P4 — Integritas paging (lanjutan fix `ctid`)

- Tambahkan primary key ke `report_mauto_cdsbo` (koordinasi DBA / pemilik ETL), lalu ganti
  tiebreaker `ctid` dengan kolom PK. `ctid` bisa berubah saat `UPDATE`/`VACUUM FULL`.
- Index `(nik, apply_date)` saat volume data bertambah (saat ini 273 baris, belum berdampak).

### P5 — Kontrak validasi (perlu konfirmasi)

- Schema menerima `nik` **atau** `cc_reff`, tetapi service mewajibkan `nik` (TC-14).
- Data tidak ditemukan dikembalikan `00` + data kosong, belum ada `44` (TC-15).
- Putuskan perilaku yang benar, lalu sesuaikan service, test, dan dokumentasi API.

## 3. Urutan eksekusi & definisi selesai

| Tahap | Item | Butuh keputusan | Definisi selesai |
|-------|------|-----------------|------------------|
| 1 | P3 logging | Tidak | PR + functional test hijau di GitHub Actions |
| 2 | P2 pool + multi-worker | DBA (batas koneksi), infra (jumlah core) | k6 `load` dibandingkan dengan baseline 2026-11-03 |
| 3 | P1 ukuran response | Ya — konsumen API | Kontrak baru disetujui, dokumentasi API diperbarui, k6 dibandingkan |
| 4 | P4 primary key | DBA / ETL | Tiebreaker `ctid` dihapus, TC-08 tetap hijau |
| 5 | P5 kontrak validasi | Ya — bisnis | Tag `@needs-confirmation` dihapus dari feature file |

Setiap tahap: test case TS-08 terkait lulus lalu tag `@known_issue` dihapus (menjadi gate), bagian *After* di
`BASELINE-ISSUES.md` diisi, k6 after fix disimpan di `tests/k6/published/after/`, functional test BDD harus hijau di CI (report Allure di GitHub Pages) dan hasil k6
dicatat di `docs/load-test/<tanggal>/` agar bisa dibandingkan dengan baseline.
