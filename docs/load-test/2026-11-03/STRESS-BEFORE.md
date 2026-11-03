# Stress Test `POST /v1/report_mauto`: sebelum perbaikan (before fix)

| Item | Nilai |
|------|-------|
| Tanggal | 2026-11-03, 16:31:54 – 16:42:58 WIB |
| Commit service | `146601d` (`main`, kode service sama dengan fix paging `ddb2345`) |
| Skenario k6 | `stress` (20 → 50 → 100 → 200 → 300 VU, lalu turun ke 0) |
| Hasil | **GAGAL threshold latency** (p95 9,6 dtk, p99 10,2 dtk); 0% error |
| Kapasitas | **±29 req/s**, jenuh sejak **±20 VU** |
| Status perbaikan | Before fix: isu README k6 §9.1–§9.4 belum diperbaiki ([BASELINE-ISSUES.md](BASELINE-ISSUES.md)) |

Dokumen ini adalah bukti **before** untuk stress test. Setelah perbaikan dari
[`docs/implementation-fixing-plan.md`](../../implementation-fixing-plan.md), jalankan ulang dengan cara yang
sama ([§8](#8-cara-menjalankan-ulang-after-fix)) lalu bandingkan.

## 1. Ringkasan

1. **Throughput mentok di ±29 req/s**, apa pun jumlah VU-nya. Dari 20 VU sampai 300 VU, RPS tetap 27–31.
   VU tambahan hanya menambah antrean.
2. **Latency naik linear terhadap jumlah VU.** p95 tembus 1 dtk pada ±27 VU, 3,5 dtk pada 100 VU, dan
   10,2 dtk pada 300 VU. Nilainya sesuai hukum Little: 300 VU ÷ 29 req/s ≈ 10,3 dtk.
3. **Tidak ada error.** 18.849 request, semua HTTP 200 dan `responseCode 00`. Antrean tidak pernah melewati
   `pool_timeout` 30 dtk (latency maks 11,9 dtk), jadi gejala §9.1 (code `99`) **belum muncul** pada 300 VU.
4. **Bottleneck: CPU 1 proses Python** (±1,1 core dari 8 core), ditambah **ukuran response** 3,6 MB per
   request (98 MB/s) yang memakan CPU untuk serialisasi JSON.
5. **Memori service naik sampai ±2 GB** pada 300 VU (±0,8 GB pada load test 20 VU). Penyebabnya response besar
   yang tertahan di antrean. Memori naik seiring konkurensi × ukuran response.
6. **Service pulih** setelah beban turun. Request terakhir (1 VU) kembali ke 163 ms.

## 2. Lingkungan & konfigurasi

| Komponen | Detail |
|----------|--------|
| Server | Intel Xeon Gold 6230R, 8 core, 62 GB RAM. Server bersama (load average ±2,4 sebelum test) |
| Service | 1 proses `uvicorn main:app` (sama dengan `main.py`), port 8915, git worktree dari commit `146601d` |
| Runtime | Python 3.13.3, FastAPI 0.115.12, SQLAlchemy 2.0.41, uvicorn 0.34.3 |
| Endpoint | Sinkron (`def`), dijalankan di threadpool AnyIO (default 40 thread) |
| Pool DB | Default SQLAlchemy: `pool_size=5`, `max_overflow=10`, `pool_timeout=30`, `pool_pre_ping=False` |
| Database | PostgreSQL UAT `report_mauto_cdsbo` (295 baris, 151 MB; `max_connections=500`) |
| Load generator | k6 0.54.0 (Docker `grafana/k6:0.54.0`, `--network host`), **di mesin yang sama** dengan service |
| Data uji | `tests/k6/data.csv`: 10 kombinasi `nik` + `apply_date` dari UAT (tidak di-commit), `limit=100` |
| Threshold | `http_req_failed<1%`, `p95<1000 ms`, `p99<2000 ms`, `business_success>99%`, `checks>99%` |

Pola beban (`tests/k6/report_mauto_stress.js`, tanpa `sleep`, jadi 1 VU = 1 request konkuren):

| Tahap | Durasi | Target VU |
|-------|--------|-----------|
| 1 | 1 m | 0 → 20 |
| 2 | 2 m | 20 → 50 |
| 3 | 2 m | 50 → 100 |
| 4 | 2 m | 100 → 200 |
| 5 | 2 m | 200 → 300 |
| 6 (recovery) | 2 m | 300 → 0 |

## 3. Hasil k6 keseluruhan

Sumber: [`k6_stress_before.txt`](k6_stress_before.txt), juga di `tests/k6/published/before/summary_stress_20261103_094255.*`.

| Metrik | Nilai |
|--------|-------|
| Total request | 18.849 (**28,55 req/s**) |
| Latency avg / p50 / p90 | 4.237 / 3.338 / 8.960 ms |
| Latency **p95 / p99** / max | **9.602 / 10.213** / 11.921 ms |
| HTTP gagal | 0,00% |
| `responseCode 00` (business_success) | 100,00% |
| Baris per response (avg / maks) | 6,18 / 20 |
| Data diterima | 63,3 GB (**98,2 MB/s**, rata-rata **3,6 MB/response**) |
| VU maks | 300 |

| Threshold | Hasil | Allure (TS-07) |
|-----------|-------|----------------|
| `http_req_failed` rate < 1% | ✓ 0,00% | TC-17 lulus |
| `http_req_duration` p95 < 1000 ms | ✗ 9.601,7 ms | TC-18 **gagal** |
| `http_req_duration` p99 < 2000 ms | ✗ 10.213,3 ms | TC-19 **gagal** |
| `business_success` rate > 99% | ✓ 100% | TC-20 lulus |
| `checks` rate > 99% | ✓ 100% | TC-21 lulus |

## 4. Hasil per tahap VU (titik jenuh)

Per 30 detik dari output mentah k6 (`--out csv`). File: [`k6_stress_before_timeline.csv`](k6_stress_before_timeline.csv).

| Detik | VU | RPS | p50 ms | p95 ms | p99 ms | MB/s |
|------:|---:|----:|-------:|-------:|-------:|-----:|
| 0 | 9 | 21,3 | 164 | 383 | 500 | 72,7 |
| 30 | 19 | 27,8 | 456 | 835 | 1.004 | 96,6 |
| 60 | 27 | 28,4 | 749 | **1.164** | 1.351 | 94,0 |
| 90 | 34 | 27,3 | 1.065 | 1.445 | 1.648 | 98,1 |
| 150 | 49 | 29,5 | 1.465 | 1.932 | 2.244 | 97,9 |
| 210 | 74 | 29,7 | 2.231 | 2.868 | 3.108 | 99,9 |
| 270 | 99 | 30,6 | 2.945 | 3.638 | 3.811 | 101,0 |
| 330 | 149 | 27,9 | 4.542 | 5.671 | 5.970 | 100,0 |
| 390 | 199 | 28,0 | 6.557 | 7.357 | 7.541 | 100,2 |
| 450 | 249 | 28,1 | 8.157 | 8.898 | 9.289 | 102,6 |
| 510 | 299 | 29,2 | 9.526 | 10.153 | 10.374 | 99,2 |
| 540 | 300 | 29,1 | 9.691 | 10.551 | 10.780 | 98,3 |
| 600 | 162 | 27,7 | 4.596 | 7.185 | 7.492 | 101,4 |
| 630 | 81 | 29,1 | 1.396 | 3.038 | 3.324 | 101,9 |
| 660 | 1 | – | 163 | 163 | 163 | – |

Ringkasan per tahap:

| Tahap | VU | Request | RPS | p50 ms | p95 ms | p99 ms | Error |
|-------|---:|--------:|----:|-------:|-------:|-------:|------:|
| 0 → 20 | 19 | 1.472 | 24,5 | 318 | 758 | 960 | 0% |
| 20 → 50 | 49 | 3.427 | 28,6 | 1.193 | 1.687 | 2.006 | 0% |
| 50 → 100 | 99 | 3.589 | 29,9 | 2.405 | 3.402 | 3.727 | 0% |
| 100 → 200 | 199 | 3.468 | 28,9 | 5.046 | 7.017 | 7.377 | 0% |
| 200 → 300 | 299 | 3.463 | 28,9 | 8.378 | 9.878 | 10.206 | 0% |
| 300 → 0 (recovery) | 300 | 3.430 | 28,6 | 6.500 | 10.187 | 10.601 | 0% |

**Titik jenuh:** RPS berhenti naik di ±28 req/s sejak ±20 VU. p95 melewati 1.000 ms pada ±27 VU.
**Kapasitas yang memenuhi threshold ±20 VU konkuren / ±28 req/s** untuk konfigurasi ini.

## 5. Resource service

File: [`resource_stress_before.csv`](resource_stress_before.csv) (sampel tiap 5 detik, proses uvicorn).

| Waktu | Kondisi | CPU % | RSS |
|-------|---------|------:|----:|
| 16:31:54 | start | – | 79 MB |
| 16:32:04 | 20 VU (ramp) | naik | 169 MB |
| 16:36:48 | ±100–124 VU | 111 | 1.843 MB |
| 16:42:34 | recovery akhir | 113 | 1.791 MB |
| 16:42:54 | setelah selesai | 113 | 1.153 MB |

- CPU tertahan di **±110% (±1,1 core)** sepanjang test, padahal server punya 8 core. Catatan: kolom CPU dari
  `ps -o %cpu` adalah rata-rata sejak proses start. Nilai yang stabil di ±110% berarti CPU terus jenuh.
- RSS maks **1.991 MB**. Memori turun lagi setelah beban turun (tidak ada indikasi leak dalam 11 menit),
  tetapi ukurannya sebanding dengan jumlah response besar yang sedang diproses.

## 6. Analisis & kaitan dengan isu §9

| Temuan | Bukti | Isu | Implikasi untuk perbaikan |
|--------|-------|-----|---------------------------|
| CPU 1 proses adalah bottleneck utama | RPS flat ±29, CPU ±110% | (P2 multi-worker) | Multi-worker diperkirakan menaikkan throughput, tetapi lihat baris berikut |
| Response 3,6 MB/request, 98 MB/s | `data_received`, kolom gambar ±99% ukuran | §9.4 | Serialisasi JSON gambar base64 memakan CPU; mengurangi kolom gambar paling berdampak per request |
| Bandwidth ±98 MB/s ≈ 0,8 Gbit/s | `data_received` | §9.4 | Data yang sama juga ditarik dari DB lewat jaringan. Dengan link 1 Gbit, multi-worker tanpa perbaikan §9.4 berpotensi mentok di jaringan (**perkiraan**, belum diukur) |
| Memori naik sampai ±2 GB pada 300 VU | `resource_stress_before.csv` | §9.4 | Multi-worker × response besar = kebutuhan RAM berlipat |
| Tidak ada code `99` walau 300 VU | 0 error, latency maks 11,9 dtk < 30 dtk | §9.1 | Antrean terjadi di CPU/threadpool, bukan di pool DB. Setelah multi-worker, pool DB menjadi relevan: `pool_timeout` & total koneksi (§9.1/§9.2) wajib diatur |
| Error tidak terlihat di level HTTP | `http_req_failed` 0% | – | Tetap pantau `business_success` & latency, bukan hanya error HTTP |

Urutan perbaikan yang disarankan berdasarkan hasil ini sama dengan fixing plan: **§9.4 (ukuran response)**
dulu, lalu **multi-worker + pool (§9.1/§9.2)**, lalu **logging (§9.3)**.

## 7. Keterbatasan

- k6 berjalan di mesin yang sama dengan service dan ikut memakai CPU. Server juga dipakai proses lain.
- Data uji hanya 10 kombinasi. Respons DB sebagian besar dari cache PostgreSQL.
- CPU/IO server database dan jaringan antara service dan DB tidak diukur.
- Satu kali run. Variasi antar run belum diukur.

## 8. Cara menjalankan ulang (after fix)

Gunakan konfigurasi yang **sama** (server, data uji, skenario, jumlah worker dicatat) agar bisa dibandingkan:

```bash
# 1. service versi yang diuji di port 8915 (catat jumlah worker & setting pool)
uvicorn main:app --host 127.0.0.1 --port 8915            # after fix: tambahkan --workers N jika P2 sudah diterapkan

# 2. sampler resource (opsional, tiap 5 detik)
PID=<pid uvicorn>; echo "timestamp,cpu_percent,rss_mb" > resource_stress_after.csv
while kill -0 $PID; do echo "$(date +%T),$(ps -o %cpu= -p $PID),$(( $(ps -o rss= -p $PID)/1024 ))" >> resource_stress_after.csv; sleep 5; done &

# 3. stress test
docker run --rm --network host --user "$(id -u):$(id -g)" -v "$PWD":/work -w /work grafana/k6:0.54.0 run \
  -e BASE_URL=http://127.0.0.1:8915 -e API_KEY_NAME=X-API-KEY -e API_KEY=<api-key> \
  -e SCENARIO=stress -e DATA_FILE=./data.csv \
  --out csv=/work/tests/k6/results/raw_stress_after.csv \
  tests/k6/report_mauto_stress.js

# 4. publikasikan ke Allure (TS-07 · Internal UAT · after fix)
cp tests/k6/results/summary_stress_<timestamp>.{json,txt} tests/k6/published/after/
```

Untuk multi-worker, sampler harus menjumlahkan semua proses worker (mis. `ps --ppid <pid master>`).
Buat `STRESS-AFTER.md` dengan struktur yang sama dengan dokumen ini dan isi tabel perbandingan di
[BASELINE-ISSUES.md](BASELINE-ISSUES.md#after-setelah-perbaikan).

## 9. File

| File | Isi |
|------|-----|
| [`k6_stress_before.txt`](k6_stress_before.txt) | Ringkasan k6 |
| [`k6_stress_before_timeline.csv`](k6_stress_before_timeline.csv) | RPS & latency per 30 detik |
| [`resource_stress_before.csv`](resource_stress_before.csv) | CPU % & RSS service per 5 detik |
| `tests/k6/published/before/summary_stress_20261103_094255.{json,txt}` | Summary untuk Allure TS-07 |
| `tests/k6/results/raw_stress_before.csv` | Output mentah k6 (32 MB, tidak di-commit) |
