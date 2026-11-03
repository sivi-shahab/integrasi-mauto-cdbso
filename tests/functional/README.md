# Functional Test — POST /v1/report_mauto

Framework: **pytest-bdd** (skenario Gherkin) + **Allure** (reporting).

| Lapisan Gherkin | Arti                 | Label Allure |
|-----------------|----------------------|--------------|
| `Feature`       | Endpoint             | feature      |
| `Rule`          | Test Scenario (TS)   | story        |
| `Scenario`      | Test Case (TC)       | title        |
| `@severity:x`   | Prioritas            | severity     |

Sumber kebenaran test scenario/test case: [`features/report_mauto.feature`](features/report_mauto.feature).

## Test Scenario & Test Case

| TS | TC | Test Case | Severity | Expected |
|----|----|-----------|----------|----------|
| TS-01 Data valid | TC-01 | Data ditemukan per nik + apply_date (9 kombinasi) | blocker | 200 / `00`, data ada, nik & tanggal cocok, urut apply_date, < 2 s |
| | TC-02 | Response memuat field utama | critical | field `application_id, nik, apply_date, status, cc_reff, branch_code, account_number` ada |
| | TC-03 | Spasi di awal/akhir nik diabaikan | normal | 200 / `00`, data ada |
| TS-02 Filter | TC-04 | Filter `cc_reff` / `branch_code` / `account_number` | critical | semua baris sesuai filter, jumlah ≤ tanpa filter |
| | TC-05 | Filter tidak cocok | normal | 200 / `00`, data kosong |
| | TC-06 | Placeholder Swagger `"string"` diabaikan | minor | jumlah = tanpa filter |
| TS-03 Paging | TC-07 | `limit=1` | normal | tepat 1 baris |
| | TC-08 | Paging `limit=5` tanpa duplikat/hilang | critical | gabungan halaman = data lengkap |
| | TC-09 | `offset` melebihi total | normal | data kosong |
| | TC-10 | `limit=0` → default 100 | minor | jumlah = data lengkap |
| | TC-11 | `limit=5000` (> maks 1000) | minor | 200 / `00` |
| | TC-12 | `limit` / `offset` negatif | normal | `40` "Limit and offset must be ≥ 0" |
| TS-04 Validasi | TC-13 | Tanpa nik & cc_reff, tanpa apply_date, limit bukan angka | critical | **400** / `40` |
| | TC-13 | apply_date salah format/tidak valid/kosong/`"string"`, nik `"string"` | critical | **200** / `40` |
| | TC-14 ⚠ | Hanya cc_reff tanpa nik | normal | 200 / `40` "nik is required" |
| TS-05 Tidak ditemukan | TC-15 ⚠ | nik tidak terdaftar / tanggal tanpa data | normal | 200 / `00`, data kosong |
| TS-06 Autentikasi | TC-16 | API key salah / kosong / tanpa header | blocker | 401 / `41` "Invalid API Key" |

| TS-07 Performa (k6) | TC-17 – TC-21 | Threshold k6: error HTTP, latency p95/p99, `business_success`, `checks` | critical/normal | lihat [tests/k6/README.md](../k6/README.md#hasil-k6-di-allure-report-ts-07) |

TS-07 tidak berasal dari feature file ini, melainkan dari summary k6 yang dikonversi oleh `tests/k6/k6_to_allure.py`.

⚠ = tag `@needs-confirmation`: expected mengikuti perilaku service saat ini dan perlu konfirmasi bisnis.

## Menjalankan

Service harus sudah berjalan. API key dibaca dari `VALID_API_KEYS` di `.env`.

```bash
uv sync --dev
uv run pytest                                   # semua test, hasil ke tests/functional/allure-results
uv run pytest -m "TC-01"                        # satu test case
uv run pytest -m "severity:blocker"             # per severity
REPORT_MAUTO_BASE_URL=http://host:8013 uv run pytest   # target lain
```

Membuat report HTML (perlu [Allure CLI](https://allurereport.org/docs/install/) + Java):

```bash
allure generate tests/functional/allure-results -o tests/functional/allure-report --clean --single-file
allure open tests/functional/allure-report
```

## CI (GitHub Actions)

Workflow [`.github/workflows/functional-test.yml`](../../.github/workflows/functional-test.yml) berjalan
pada push ke `main`, pull request, dan manual (`workflow_dispatch`):

1. Menjalankan Postgres 16 sebagai service container.
2. Membuat tabel dari [`ci/schema.sql`](ci/schema.sql) (struktur tabel UAT, tanpa data) dan mengisi
   data sintetis via [`ci/seed.py`](ci/seed.py). Tidak terhubung ke DB internal.
3. Menjalankan service (uvicorn), `pytest`, lalu k6 skenario `smoke` (atau `load` via *Run workflow*)
   dan mengonversi hasilnya ke Allure (TS-07), ditambah hasil run internal di `tests/k6/published/`.
4. Membuat Allure report (dengan trend dari run sebelumnya), upload sebagai artifact, dan
   untuk `main` mempublikasikannya ke GitHub Pages (branch `gh-pages`):
   <https://sivi-shahab.github.io/integrasi-mauto-cdbso/>

Setup satu kali: **Settings → Pages → Source: Deploy from a branch → `gh-pages` / root**
(branch `gh-pages` dibuat otomatis pada run pertama di `main`).

Menjalankan setup CI secara lokal:

```bash
docker run -d --rm --name pg-ci -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=report_mauto -p 127.0.0.1:55433:5432 postgres:16
export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55433 POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_DB=report_mauto
uv run python tests/functional/ci/seed.py
```

Jika skenario baru membutuhkan data lain, tambahkan kombinasi di `COMBOS` pada `ci/seed.py`.

## Catatan keamanan data

Report **tidak** melampirkan body response utuh, karena berisi data pribadi nasabah dan foto
selfie/KTP base64 (bisa > 10 MB per request). Yang dilampirkan hanya ringkasan
(HTTP status, responseCode, jumlah baris, ukuran, waktu, `application_id`/`apply_date`/`status`).
API key disamarkan (`'***'`) di parameter step dan traceback.
