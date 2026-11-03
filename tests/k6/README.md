# Stress Test k6 — `POST /v1/report_mauto`

Dokumentasi untuk script performance test `report_mauto_stress.js`. Baca seluruh
dokumen ini sebelum menjalankan test, terutama bagian
[Sebelum Menjalankan](#5-sebelum-menjalankan-checklist) dan
[Risiko & Hal yang Perlu Diperhatikan](#9-risiko--hal-yang-perlu-diperhatikan).

> **Status:** script belum pernah dijalankan (k6 belum terpasang di server
> development saat script dibuat). Jalankan skenario `smoke` terlebih dahulu
> untuk memastikan script berfungsi.

---

## Daftar Isi

1. [Tujuan](#1-tujuan)
2. [Struktur File](#2-struktur-file)
3. [Endpoint yang Diuji](#3-endpoint-yang-diuji)
4. [Instalasi k6](#4-instalasi-k6)
5. [Sebelum Menjalankan (Checklist)](#5-sebelum-menjalankan-checklist)
6. [Konfigurasi (Environment Variable)](#6-konfigurasi-environment-variable)
7. [Skenario Test](#7-skenario-test)
8. [Cara Menjalankan](#8-cara-menjalankan)
9. [Risiko & Hal yang Perlu Diperhatikan](#9-risiko--hal-yang-perlu-diperhatikan)
10. [Cara Kerja Script](#10-cara-kerja-script)
11. [Threshold (Kriteria Lulus)](#11-threshold-kriteria-lulus)
12. [Membaca Hasil](#12-membaca-hasil)
13. [Menyimpan Hasil ke File](#13-menyimpan-hasil-ke-file)
14. [Monitoring Selama Test](#14-monitoring-selama-test)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Tujuan

Mengukur perilaku endpoint `POST /v1/report_mauto` di bawah beban:

- **Kapasitas** — berapa request/detik (RPS) yang sanggup dilayani dengan latency wajar.
- **Titik jenuh** — pada jumlah user (VU) berapa latency naik tajam atau error mulai muncul.
- **Bottleneck** — komponen mana yang habis duluan (worker aplikasi, connection pool DB, CPU DB).
- **Pemulihan** — apakah service kembali normal setelah beban diturunkan.

## 2. Struktur File

```
tests/k6/
├── README.md               # dokumen ini
├── report_mauto_stress.js  # script k6
├── data.example.csv        # contoh format data uji (bukan data asli)
├── .gitignore              # mengabaikan data.csv (berisi NIK)
└── results/                # output handleSummary (isi di-ignore git)
```

## 3. Endpoint yang Diuji

| Item          | Nilai                                                         |
|---------------|---------------------------------------------------------------|
| Method / Path | `POST /v1/report_mauto`                                       |
| Autentikasi   | Header API key (nama header = `API_KEY_NAME` di `.env`, default `.env.sample`: `X-API-KEY`; nilai = `VALID_API_KEYS`) |
| Content-Type  | `application/json`                                            |
| Kode          | `app/api/v1/endpoints/report_mauto_endpoints.py` → `app/service/report_mauto_service.py` |

### Request body

| Field            | Wajib | Keterangan                                  |
|------------------|-------|---------------------------------------------|
| `apply_date`     | Ya    | Format `ddmmyyyy`, contoh `01012026`        |
| `nik`            | Ya*   | Wajib di service v1 (lihat catatan)         |
| `cc_reff`        | Tidak | Filter tambahan                             |
| `branch_code`    | Tidak | Filter tambahan                             |
| `account_number` | Tidak | Filter tambahan                             |
| `limit`          | Tidak | Default 100, maksimum efektif 1000          |
| `offset`         | Tidak | Default 0                                   |

\* Schema mengizinkan `nik` **atau** `cc_reff`, tetapi service v1 menolak request
tanpa `nik`. Karena itu data uji **harus selalu berisi `nik`**.

Contoh:

```json
{ "nik": "3171234567890001", "apply_date": "01012026", "limit": 100, "offset": 0 }
```

### Query yang dieksekusi

```sql
SELECT * FROM public.report_mauto_cdsbo
WHERE nik = :nik
  AND apply_date >= :date_start AND apply_date < :date_end
  AND (... filter opsional ...)
ORDER BY apply_date
LIMIT :limit OFFSET :offset
```

### Pola response — penting untuk interpretasi hasil

| Kondisi                                | HTTP | `responseCode` |
|----------------------------------------|------|----------------|
| Sukses (termasuk data kosong `[]`)     | 200  | `00`           |
| `apply_date`/`nik` tidak valid (service)| **200** | `40`        |
| Validasi Pydantic gagal                | 400  | `40`           |
| API key salah / kosong                 | 401  | `41`           |
| Error DB (termasuk pool habis/timeout) | **200** | `99`        |
| Exception lain                         | 500  | `99`           |

Perhatikan: **error dari service dikembalikan dengan HTTP 200**. Metrik bawaan
k6 `http_req_failed` tidak akan menangkapnya, sehingga script menambahkan
pengecekan `responseCode` sendiri (lihat [bagian 10](#10-cara-kerja-script)).

## 4. Instalasi k6

k6 adalah binary tunggal, tidak perlu Node.js.

**Ubuntu/Debian:**

```bash
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6
```

**Tanpa akses root / tanpa internet ke repo apt:** unduh binary dari
<https://github.com/grafana/k6/releases>, ekstrak, jalankan `./k6`.

**Docker:**

```bash
docker run --rm -i --network host -v "$PWD/tests/k6:/scripts" grafana/k6 run /scripts/report_mauto_stress.js -e ...
```

Cek: `k6 version`.

> **Rekomendasi:** jalankan k6 dari mesin **terpisah** dari server aplikasi.
> Jika k6 berjalan di mesin yang sama, k6 ikut memakan CPU/RAM sehingga hasil
> tidak akurat.

## 5. Sebelum Menjalankan (Checklist)

- [ ] **Izin & koordinasi** — target environment sudah disetujui. **Jangan
      menjalankan ke production** tanpa persetujuan tim terkait (aplikasi, DBA,
      infra). Stress test sengaja membebani server sampai batas.
- [ ] **Environment target** — idealnya environment staging/UAT dengan spesifikasi
      dan volume data mendekati production.
- [ ] **Database** — informasikan DBA; DB yang sama mungkin dipakai service lain.
- [ ] **API key** — siapkan nilai `API_KEY_NAME` dan `VALID_API_KEYS` dari `.env`
      environment target. Jangan commit API key ke repository.
- [ ] **Data uji** — siapkan CSV berisi kombinasi `nik` + `apply_date` yang
      **benar-benar ada** di tabel (lihat [bagian 6.1](#61-data-uji-csv)).
- [ ] **Data sensitif** — NIK adalah data pribadi. Simpan CSV di luar repository
      atau pastikan tidak ikut ter-commit; hapus setelah selesai.
- [ ] **Monitoring siap** — siapkan cara memantau CPU/RAM server, log aplikasi,
      dan koneksi PostgreSQL (lihat [bagian 14](#14-monitoring-selama-test)).
- [ ] **Konfigurasi server dicatat** — jumlah worker uvicorn, spesifikasi CPU/RAM,
      setting pool DB. Tanpa ini, hasil test sulit dibandingkan antar run.
- [ ] **Smoke test dulu** — jalankan `SCENARIO=smoke` dan pastikan semua check hijau.

## 6. Konfigurasi (Environment Variable)

Semua konfigurasi diberikan lewat flag `-e NAMA=nilai`.

| Variable       | Default                  | Keterangan                                                  |
|----------------|--------------------------|-------------------------------------------------------------|
| `BASE_URL`     | `http://localhost:8013`  | URL service (tanpa `/v1`). Port default `main.py` = 8013.   |
| `API_KEY_NAME` | `X-API-KEY`              | Nama header API key (sesuai `.env` target)                  |
| `API_KEY`      | *(kosong)*               | Nilai API key. **Wajib diisi**, kalau tidak semua → 401     |
| `SCENARIO`     | `stress`                 | `smoke` / `load` / `stress` / `spike` / `soak`              |
| `DATA_FILE`    | *(kosong)*               | Path CSV data uji, **relatif terhadap folder script**       |
| `NIK`          | `3171234567890001`       | Dipakai jika `DATA_FILE` kosong (nilai dummy!)              |
| `APPLY_DATE`   | `01012026`               | Dipakai jika `DATA_FILE` kosong (nilai dummy!)              |
| `LIMIT`        | `100`                    | Nilai `limit` di request body                               |
| `RESULT_DIR`   | `tests/k6/results`       | Folder file hasil. Relatif terhadap **direktori tempat `k6 run` dijalankan** (bukan folder script). Folder harus sudah ada |

### 6.1 Data uji (CSV)

Format (header wajib ada, kolom opsional boleh dikosongkan):

```csv
nik,apply_date,cc_reff,branch_code,account_number
3171234567890001,01012026,,,
3171234567890002,15022026,,,
```

Tips:

- Gunakan **banyak baris berbeda** (ratusan–ribuan). Jika hanya satu NIK,
  PostgreSQL akan melayani dari cache dan hasil terlihat lebih bagus dari kenyataan.
- Campurkan NIK yang datanya banyak dan sedikit agar realistis.
- Contoh query untuk mengambil data uji (jalankan oleh DBA/di environment target):

  ```sql
  SELECT nik, to_char(apply_date, 'DDMMYYYY') AS apply_date
  FROM public.report_mauto_cdsbo
  WHERE nik IS NOT NULL
  GROUP BY nik, to_char(apply_date, 'DDMMYYYY')
  LIMIT 1000;
  ```

  Simpan hasilnya sebagai CSV dengan header `nik,apply_date`.
- Parser CSV di script sederhana: **jangan gunakan koma atau tanda kutip di dalam nilai**.

## 7. Skenario Test

Pilih dengan `-e SCENARIO=...`. VU (virtual user) = satu "user" yang mengirim
request terus-menerus tanpa jeda.

| Skenario | Pola beban                                                      | Durasi   | Tujuan                                  |
|----------|-----------------------------------------------------------------|----------|-----------------------------------------|
| `smoke`  | 1 VU konstan                                                    | 30 dtk   | Validasi script, API key, dan data      |
| `load`   | naik ke 20 VU (1m) → tahan 20 VU (3m) → turun (1m)              | 5 mnt    | Performa di beban normal (baseline)     |
| `stress` | 20 → 50 → 100 → 200 → 300 VU (masing-masing 1–2m) → turun ke 0  | 11 mnt   | Mencari titik jenuh & cek pemulihan     |
| `spike`  | 10 VU → lonjak ke 300 VU dalam 10 dtk → tahan 1m → turun        | ~3 mnt   | Reaksi terhadap lonjakan mendadak       |
| `soak`   | 30 VU konstan                                                   | 30 mnt   | Kebocoran memori / koneksi jangka panjang |

**Urutan yang disarankan:** `smoke` → `load` → `stress` → (opsional) `spike` / `soak`.
Beri jeda beberapa menit antar run agar server kembali idle.

Karena tidak ada `sleep`, 1 VU ≈ 1 request berjalan bersamaan. Jadi 300 VU
berarti hingga **300 request konkuren** — jauh lebih berat daripada 300 user
manusia. Untuk mensimulasikan user nyata, tambahkan `sleep(1)` di akhir fungsi
`default` (lihat komentar di script).

Angka VU dan durasi bisa diubah langsung di objek `scenarios` dalam script.

## 8. Cara Menjalankan

Jalankan dari root repository.

**1) Smoke test:**

```bash
k6 run tests/k6/report_mauto_stress.js \
  -e BASE_URL=http://<host>:8013 \
  -e API_KEY_NAME=X-API-KEY \
  -e API_KEY=<api-key> \
  -e DATA_FILE=./data.csv \
  -e SCENARIO=smoke
```

> `DATA_FILE=./data.csv` berarti file `tests/k6/data.csv` (relatif ke folder script).

**2) Load test (baseline):** sama, ganti `-e SCENARIO=load`.

**3) Stress test:** sama, ganti `-e SCENARIO=stress`.

Agar API key tidak tersimpan di history shell:

```bash
read -s API_KEY && export API_KEY
k6 run tests/k6/report_mauto_stress.js -e API_KEY="$API_KEY" ...
```

**Menghentikan test:** tekan `Ctrl+C` satu kali (k6 berhenti dengan rapi dan
tetap menampilkan ringkasan). Tekan dua kali untuk berhenti paksa.

## 9. Risiko & Hal yang Perlu Diperhatikan

### 9.1 Connection pool database kemungkinan besar menjadi bottleneck

`app/db/session.py` memakai `create_engine(DATABASE_URL)` tanpa konfigurasi pool,
sehingga memakai default SQLAlchemy:

| Setting        | Default | Arti                                                   |
|----------------|---------|--------------------------------------------------------|
| `pool_size`    | 5       | koneksi tetap per proses worker                        |
| `max_overflow` | 10      | koneksi tambahan saat ramai                            |
| `pool_timeout` | 30 dtk  | lama menunggu koneksi kosong sebelum error             |

Artinya **maksimal 15 query bersamaan per worker**. Endpoint ini sinkron (`def`),
jadi FastAPI menjalankannya di threadpool (default ±40 thread). Saat VU melebihi
kapasitas tersebut, request akan **antre** dan latency naik. Jika antre lebih
dari 30 detik, akan terjadi `TimeoutError` dari pool → ditangkap service →
response **HTTP 200 dengan `responseCode: "99"`**.

Gejala di hasil k6: `business_success` turun, `non_success_response_code{code:99}`
naik, padahal `http_req_failed` tetap rendah.

Ini **temuan yang wajar** untuk dicatat sebagai hasil stress test, bukan bug
di script.

### 9.2 Jumlah koneksi ke PostgreSQL

Total koneksi maksimum = `jumlah worker × 15`. Pastikan nilai ini tidak melebihi
`max_connections` PostgreSQL (cek: `SHOW max_connections;`) dikurangi koneksi
service lain.

### 9.3 Log aplikasi

Setiap request sukses menulis satu baris log `INFO`. Pada ribuan RPS, folder
`logs/` bisa membesar cepat. Pastikan disk cukup, dan bersihkan/rotasi setelah test.

### 9.4 Ukuran response

Query memakai `SELECT *` dari tabel lebar (±180 kolom, termasuk kolom seperti
`request_base64_ktp` dan `selfie` yang bisa berukuran besar). Dengan `limit=100`,
satu response bisa besar. Bandwidth jaringan bisa menjadi bottleneck — pantau
metrik `data_received` di hasil k6.

### 9.5 Batas mesin k6

Untuk 300 VU, mesin k6 umumnya butuh ±1–2 GB RAM. Jika muncul error
`too many open files`, naikkan limit: `ulimit -n 65535`.

## 10. Cara Kerja Script

1. **Init** — memuat data uji dari CSV (atau `NIK`/`APPLY_DATE`) ke `SharedArray`
   sehingga dibagi bersama semua VU tanpa duplikasi memori.
2. **`setup()`** — dijalankan sekali sebelum beban dimulai. Mengirim satu request
   menggunakan baris data pertama. Jika HTTP status ≠ 200 (misalnya API key salah,
   URL salah, server mati), **test dibatalkan** sebelum beban dikirim.
3. **Fungsi `default`** — dijalankan berulang oleh setiap VU:
   - pilih baris data secara acak;
   - kirim `POST` dengan body `{...baris, limit, offset: 0}` dan timeout 30 detik;
   - jalankan check:
     - `status is 200`
     - `body is JSON`
     - `responseCode is 00`
     - `data is array`
   - catat metrik custom.

### Metrik custom

| Metrik                       | Tipe    | Arti                                                         |
|------------------------------|---------|--------------------------------------------------------------|
| `business_success`           | Rate    | Persentase response dengan `responseCode == "00"`            |
| `rows_returned`              | Trend   | Jumlah baris `data` per response sukses                      |
| `non_success_response_code`  | Counter | Jumlah response gagal, dengan tag `code` (mis. `40`, `99`, `http_401`) |

## 11. Threshold (Kriteria Lulus)

| Threshold              | Nilai             | Arti                                   |
|------------------------|-------------------|----------------------------------------|
| `http_req_failed`      | `rate < 0.01`     | Error HTTP (status ≥ 400 / timeout) < 1% |
| `http_req_duration`    | `p(95) < 1000`    | 95% request selesai < 1 detik          |
| `http_req_duration`    | `p(99) < 2000`    | 99% request selesai < 2 detik          |
| `business_success`     | `rate > 0.99`     | > 99% response `responseCode = "00"`   |
| `checks`               | `rate > 0.99`     | > 99% check lulus                      |

Nilai di atas adalah **asumsi awal**, bukan SLA resmi. Sesuaikan dengan SLA yang
disepakati (ubah di `options.thresholds` dalam script).

Untuk skenario `stress` dan `spike`, threshold **memang diharapkan gagal** pada
tahap beban tertinggi — tujuan test ini adalah menemukan di VU berapa kegagalan
mulai terjadi. Jika threshold gagal, k6 keluar dengan exit code `99`.

## 12. Membaca Hasil

Di akhir run, k6 menampilkan ringkasan. Bagian penting:

```
✓ status is 200
✓ responseCode is 00
...
business_success...........: 99.95%
http_req_duration..........: avg=120ms med=95ms p(90)=210ms p(95)=320ms p(99)=800ms max=2.1s
http_req_failed............: 0.00%
http_reqs..................: 45000  150/s
iterations.................: 45000
rows_returned..............: avg=3.2 ...
vus_max....................: 300
```

*(angka di atas hanya ilustrasi)*

| Metrik                | Cara membaca                                                         |
|-----------------------|----------------------------------------------------------------------|
| `http_reqs` (…/s)     | Throughput (RPS) rata-rata selama test                               |
| `http_req_duration`   | Latency end-to-end. Fokus pada **p95 & p99**, bukan rata-rata       |
| `http_req_waiting`    | Waktu tunggu server (TTFB) — mencerminkan waktu proses aplikasi + DB |
| `http_req_failed`     | Error di level HTTP                                                  |
| `business_success`    | Error di level bisnis (termasuk HTTP 200 + code `99`)               |
| `rows_returned`       | Jika rata-rata ≈ 0, data uji tidak cocok → hasil tidak representatif |
| `data_received`       | Total bandwidth response                                             |

### Menentukan titik jenuh (skenario `stress`)

Ringkasan k6 hanya menampilkan rata-rata keseluruhan. Untuk melihat per tahap VU,
gunakan `--out json` atau web dashboard (lihat [bagian 13](#13-menyimpan-hasil-ke-file)) lalu
amati kapan:

- p95 latency mulai naik tajam, **atau**
- `business_success` / `checks` mulai turun di bawah target, **atau**
- RPS berhenti naik walaupun VU terus bertambah (server sudah jenuh).

Jumlah VU pada titik itu = kapasitas maksimal untuk konfigurasi server saat test.

### Mencatat hasil

Untuk setiap run, catat: tanggal, commit git, environment, jumlah worker uvicorn,
spesifikasi server, setting pool DB, skenario, jumlah baris data uji, dan
ringkasan k6. Tanpa catatan ini, run berikutnya tidak bisa dibandingkan.

## 13. Menyimpan Hasil ke File

Script memiliki fungsi `handleSummary` yang otomatis dijalankan k6 di akhir
setiap run (termasuk saat dihentikan dengan `Ctrl+C`). Hasilnya:

| Output                                              | Isi                                                     |
|-----------------------------------------------------|---------------------------------------------------------|
| `<RESULT_DIR>/summary_<scenario>_<YYYYMMDD_HHMMSS>.json` | Data summary lengkap dari k6 + blok `meta` (scenario, endpoint, data file, jumlah baris, limit, waktu selesai) |
| `<RESULT_DIR>/summary_<scenario>_<YYYYMMDD_HHMMSS>.txt`  | Ringkasan yang mudah dibaca (lihat contoh di bawah)     |
| Terminal (stdout)                                   | Ringkasan yang sama dengan `.txt` + lokasi file         |

Nama file memakai timestamp sehingga **run sebelumnya tidak tertimpa**.

Catatan:

- Karena `handleSummary` didefinisikan, **ringkasan bawaan k6 tidak lagi
  ditampilkan**; yang tampil adalah ringkasan dari script ini.
- Formatter ditulis sendiri di script (tidak mengimpor `jslib.k6.io`), sehingga
  bisa dipakai di jaringan tanpa akses internet.
- k6 **tidak bisa membuat folder**. Folder `tests/k6/results/` sudah disediakan
  di repository. Jika memakai `RESULT_DIR` lain, buat dulu dengan `mkdir -p`.
- Default `RESULT_DIR` mengasumsikan k6 dijalankan dari **root repository**. Jika
  dijalankan dari folder lain, set `-e RESULT_DIR=...`. Jika folder tidak ditemukan,
  k6 menampilkan error saat menulis file, tetapi ringkasan tetap tampil di terminal.
- Isi folder `results/` di-ignore oleh git (lihat `results/.gitignore`).

Contoh isi file `.txt` *(angka hanya ilustrasi)*:

```
======================================================================
 k6 summary — POST /v1/report_mauto
======================================================================
 Scenario   : stress
 Target     : http://10.x.x.x:8013/v1/report_mauto
 Data rows  : 1000 (./data.csv)
 Limit      : 100
 Selesai    : Tue Nov 03 2026 10:30:00 GMT+0700
 Durasi     : 660.2s

--- Checks -----------------------------------------------------------
 ✓ status is 200          100.00% (45000 ✓ / 0 ✗)
 ✓ body is JSON           100.00% (45000 ✓ / 0 ✗)
 ✗ responseCode is 00     98.70% (44415 ✓ / 585 ✗)
 ✗ data is array          98.70% (44415 ✓ / 585 ✗)

--- Metrics ----------------------------------------------------------
 http_reqs................... 45001 (68.16/s)
 http_req_duration........... avg=850.12ms min=12.30ms med=420.55ms p(90)=2100.00ms p(95)=3050.40ms p(99)=8200.10ms max=30000.00ms
 http_req_failed............. 0.00% (0 ✓ / 45001 ✗)
 business_success............ 98.70% (44415 ✓ / 585 ✗)
 ...

--- Thresholds -------------------------------------------------------
 ✓ http_req_failed rate<0.01
 ✗ http_req_duration p(95)<1000
 ...

 HASIL: GAGAL — ada threshold yang tidak terpenuhi
======================================================================
```

> Untuk `http_req_failed`, "✓" berarti request yang **gagal**, jadi `0.00%` adalah
> kondisi bagus. Ini konvensi bawaan k6.

### Output tambahan (opsional)

Summary hanya berisi agregat seluruh run. Untuk analisis per tahap VU (mencari
titik jenuh), tambahkan data mentah:

```bash
k6 run tests/k6/report_mauto_stress.js ... \
  --out json=tests/k6/results/raw_stress_$(date +%Y%m%d_%H%M).json
```

File ini berisi setiap data point dan bisa berukuran ratusan MB untuk stress test.

Untuk grafik real-time, gunakan web dashboard bawaan k6 (versi ≥ 0.49):

```bash
K6_WEB_DASHBOARD=true \
K6_WEB_DASHBOARD_EXPORT=tests/k6/results/report_stress.html \
k6 run tests/k6/report_mauto_stress.js ...
```

Buka `http://localhost:5665` selama test berjalan; laporan HTML tersimpan saat test selesai.

## 14. Monitoring Selama Test

Hasil k6 hanya menunjukkan sisi client. Pantau juga sisi server:

**Server aplikasi:**

```bash
top            # atau htop: CPU & RAM proses uvicorn
tail -f logs/*.log | grep -iE "error|exception|timeout"
```

**PostgreSQL** (jalankan oleh DBA atau user dengan akses):

```sql
-- jumlah koneksi dari aplikasi, per state
SELECT state, count(*) FROM pg_stat_activity
WHERE datname = '<nama_db>' GROUP BY state;

-- query yang sedang berjalan lama
SELECT pid, now() - query_start AS durasi, state, left(query, 80)
FROM pg_stat_activity
WHERE datname = '<nama_db>' AND state <> 'idle'
ORDER BY durasi DESC LIMIT 10;
```

Juga periksa apakah ada index pada kolom filter (`nik`, `apply_date`):

```sql
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'report_mauto_cdsbo';
```

Jika tidak ada index pada `nik`/`apply_date`, setiap request akan melakukan full
table scan dan performa akan turun drastis seiring jumlah data.

## 15. Troubleshooting

| Gejala                                                   | Kemungkinan penyebab & solusi                                         |
|----------------------------------------------------------|-----------------------------------------------------------------------|
| `Sanity check gagal: status=401`                         | `API_KEY` / `API_KEY_NAME` salah atau kosong                          |
| `Sanity check gagal: status=0` / `connection refused`    | `BASE_URL` salah, server mati, atau firewall                          |
| `Sanity check gagal: status=400`                         | Baris pertama CSV tidak valid (format `apply_date` bukan `ddmmyyyy`, `nik` kosong) |
| `SCENARIO tidak dikenal`                                 | Nilai `SCENARIO` salah ketik                                           |
| `open ... no such file`                                  | `DATA_FILE` tidak ditemukan — path relatif terhadap folder script     |
| Error menulis `summary_*.json` / `.txt` di akhir test   | Folder `RESULT_DIR` tidak ada — jalankan k6 dari root repo atau `mkdir -p` folder tujuan |
| Semua check hijau tapi `rows_returned` avg = 0           | Data uji tidak ada di DB → ganti data uji                             |
| `responseCode is 00` gagal, code `40`                    | Ada baris CSV yang tidak valid                                         |
| `responseCode is 00` gagal, code `99` saat VU tinggi     | DB error / pool habis (lihat [9.1](#91-connection-pool-database-kemungkinan-besar-menjadi-bottleneck)) |
| `request timeout` / `http_req_failed` naik               | Server tidak sanggup menjawab dalam 30 detik — server jenuh           |
| `too many open files` di mesin k6                        | `ulimit -n 65535` sebelum menjalankan k6                              |
| `dial: i/o timeout` banyak                               | Batas koneksi di load balancer/proxy, atau mesin k6 kehabisan port    |
