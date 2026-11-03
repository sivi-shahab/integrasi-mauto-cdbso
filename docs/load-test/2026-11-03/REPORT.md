# Laporan Load Test & Perbandingan Fix — POST /v1/report_mauto

Tanggal: 2026-11-03
Yang dibandingkan:

| Label | Kode | Commit |
|-------|------|--------|
| **Baseline** | `main` (kode existing) | `dfe60eb` |
| **Fix** | branch `fix/report-mauto-paging` (refactor service + fix paging) | `3abf776` |

## 1. Ringkasan

- **Performa: tidak berubah.** Kedua versi lulus semua threshold load test (20 VU, 5 menit) dengan angka yang praktis
  identik (~26,5 req/s, p95 ≈ 1 detik). Fix ini memang soal kebenaran data, bukan performa.
- **Kebenaran fungsional: 24/37 → 37/37 test lulus.** Fix menyelesaikan urutan data, normalisasi input dan paging.
- **Bug paging (TC-08) bukan berasal dari `main`**, melainkan dari refactor yang menambah `ORDER BY apply_date`.
  Fix `ORDER BY apply_date, ctid` menutupnya. Lihat §2.1.
- **Perlu konfirmasi bisnis:** refactor membuat `nik` **wajib**. Di `main`, pencarian hanya dengan `cc_reff` (tanpa nik)
  **didukung**; di versi fix ditolak. Ini *breaking change* bagi klien yang memakai cc_reff saja. Lihat §2.2.
- **Risiko performa:** p95 versi fix 997,6 ms, hanya 2,4 ms di bawah threshold 1000 ms. Bottleneck adalah CPU
  satu proses Python (±1 core penuh), terutama untuk serialisasi response yang besar (rata-rata ~3,4 MB karena foto
  selfie/KTP base64). Lihat §4.

## 2. Apa yang di-fix

### 2.1 Paging & urutan data (TC-08)

| Versi | Query | Hasil |
|-------|-------|-------|
| `main` | tanpa `ORDER BY` | Paging konsisten dalam pengujian, tetapi **urutan tidak dijamin** dan hasil tidak terurut (TC-01 gagal) |
| refactor (sebelum fix) | `ORDER BY apply_date` | **Bug:** baris ganda/hilang antar halaman |
| **fix** | `ORDER BY apply_date, ctid` | Terurut dan paging konsisten |

Penyebab: tabel `report_mauto_cdsbo` tidak punya primary key/unique key dan `apply_date` tidak unik (20 baris hanya
punya 10 nilai `apply_date` berbeda). Dengan `LIMIT`, PostgreSQL memakai *top-N heapsort* sehingga urutan baris
dengan `apply_date` sama bisa berbeda antar halaman. `ctid` (alamat fisik baris) menjadi tiebreaker unik.

Verifikasi langsung di SQL (nik `3201133107990002`, tanggal 29-09-2025, 20 baris; semua halaman digabung lalu
dibandingkan dengan hasil lengkap):

| Page size | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 10 |
|---|---|---|---|---|---|---|---|---|
| tanpa ORDER BY (`main`) | OK | OK | OK | OK | OK | OK | OK | OK |
| `ORDER BY apply_date` (refactor) | OK | OK | OK | OK | **X** | OK | **X** | OK |
| `ORDER BY apply_date, ctid` (fix) | OK | OK | OK | OK | OK | OK | OK | OK |

Batasan: `ctid` berubah jika baris di-UPDATE atau tabel di-`VACUUM FULL`. Solusi jangka panjang: tambahkan primary
key ke tabel dan pakai itu sebagai tiebreaker.

### 2.2 Perubahan perilaku lain (refactor service)

| Area | `main` | Fix | Status |
|------|--------|-----|--------|
| Filter tanggal | `DATE(apply_date) = :d` | `apply_date >= :d AND apply_date < :d+1` | Perbaikan: bisa memakai index jika nanti dibuat |
| nik dengan spasi (`" 3201… "`) | data kosong | spasi di-trim, data ditemukan | Perbaikan |
| Placeholder Swagger `"string"` pada filter | difilter apa adanya → data kosong | diabaikan | Perbaikan |
| `limit=0` | `LIMIT 0` → data kosong | default 100 | Perbaikan |
| `limit` sangat besar | tanpa batas | maksimum 1000 | Perbaikan (proteksi) |
| apply_date tidak valid / kosong / `"string"` | `40` "Invalid date format. Use ddmmyyyy." | `40` "apply_date is required with format ddmmyyyy." | Pesan berubah |
| nik `"string"` | `00` dengan data kosong | `40` "nik is required." | Perbaikan |
| **Hanya cc_reff (tanpa nik)** | **didukung**, dicari per tanggal + cc_reff | **ditolak** `40` "nik is required." | ⚠ **Breaking change, perlu konfirmasi** |

## 3. Hasil functional test (pytest-bdd, 37 test)

| | `main` | Fix |
|---|---|---|
| Lulus | 24 | **37** |
| Gagal | 13 | 0 |

Rincian 13 kegagalan `main`:

| Test | Penyebab di `main` | Jenis |
|------|-------------------|-------|
| TC-01 (4 dari 9 data) | Hasil tidak terurut berdasarkan apply_date | Bug di `main` |
| TC-03 | nik dengan spasi tidak ditemukan | Bug di `main` |
| TC-06 | Placeholder `"string"` diperlakukan sebagai filter | Bug di `main` |
| TC-10 | `limit=0` mengembalikan 0 baris | Bug di `main` |
| TC-13 (4 kasus apply_date) | Pesan error berbeda (responseCode tetap `40`) | Perubahan pesan, bukan bug |
| TC-13 (nik `"string"`) | `00` dengan data kosong, bukan `40` | Bug di `main` |
| TC-14 | cc_reff saja diterima (`00`) | Perbedaan kontrak, lihat §2.2 |

Catatan: test case ditulis mengikuti perilaku versi fix, sehingga perubahan pesan dan kontrak ikut tercatat sebagai
"gagal" pada `main`.

## 4. Hasil load test (k6, skenario `load`)

Skenario: ramp 0 → 20 VU (1 menit), tahan 20 VU (3 menit), ramp turun (1 menit). Tanpa think time.
Data: 10 baris (9 kombinasi nik + apply_date unik) yang ada di database, `limit=100`.

| Metrik | Baseline (`main`) | Fix | Selisih |
|--------|------------------|-----|---------|
| Total request | 7.945 | 7.967 | +0,3% |
| Throughput | 26,47 req/s | 26,54 req/s | +0,3% |
| HTTP error | 0% | 0% | — |
| responseCode `00` | 100% | 100% | — |
| Latency rata-rata | 569,6 ms | 568,3 ms | −0,2% |
| Latency median | 581,1 ms | 579,9 ms | −0,2% |
| Latency p90 | 886,4 ms | 891,6 ms | +0,6% |
| Latency p95 (threshold < 1000) | 979,4 ms ✓ | 997,6 ms ✓ | +1,9% |
| Latency p99 (threshold < 2000) | 1.191,0 ms ✓ | 1.217,9 ms ✓ | +2,3% |
| Latency maksimum | 1.915,2 ms | 1.967,8 ms | +2,7% |
| Data diterima | 26,71 GB (91,1 MB/s) | 26,97 GB (92,0 MB/s) | +1,0% |
| CPU service (total) | 333,0 CPU-detik (~111%) | 326,7 CPU-detik (~109%) | −1,9% |
| Memori service puncak | 882 MB | 871 MB | −1,2% |
| **Hasil threshold** | **LULUS** | **LULUS** | |

Selisih ±3% masih dalam variasi normal antar run; **tidak ada perubahan performa yang berarti.**
Tambahan `ORDER BY` tidak berdampak karena per request hanya ±1–20 baris yang diurutkan.

Timeline resource versi fix (sampel tiap 5 detik, file `resource_fix.csv`):
CPU naik ke ±108% dalam menit pertama (saat ramp ke 20 VU) dan bertahan di 106–118% sampai selesai.
Memori (RSS) naik dari 118 MB ke ±780 MB lalu stabil. Untuk baseline hanya tersedia angka total, karena sampler
saat itu salah mengambil PID.

### Analisis

1. **Service jenuh di ±26 req/s.** Dengan 1 VU (smoke test): 11 req/s @ 61 ms. Dengan 20 VU throughput hanya naik ke
   26 req/s sementara latency naik ±9×, artinya request mengantre.
2. **Bottleneck: CPU satu proses Python.** CPU tertahan di ±1 core penuh. Service berjalan sebagai 1 proses uvicorn
   (`main.py`), sehingga core lain di server (8 core) tidak terpakai.
3. **Response sangat besar.** Rata-rata ~3,4 MB per request; satu kombinasi (20 baris) mencapai 13,5 MB. Kolom
   `selfie` dan `request_base64_ktp` (base64) mendominasi ukuran, sehingga serialisasi JSON memakan CPU.
4. **Database bukan bottleneck saat ini.** Tabel hanya 273 baris (151 MB, mayoritas gambar); query plan memakai
   sort kecil. Index `(nik, apply_date)` baru relevan saat tabel tumbuh. Catatan: CPU/IO server database tidak diukur.

## 5. Rekomendasi

| Prioritas | Rekomendasi | Perkiraan dampak |
|-----------|-------------|------------------|
| 1 | Konfirmasi kontrak: apakah pencarian hanya dengan cc_reff masih harus didukung (§2.2) | Mencegah breaking change ke klien |
| 2 | Jangan kirim `selfie` / `request_base64_ktp` di endpoint list; sediakan endpoint detail/terpisah untuk gambar | Ukuran response dan CPU turun drastis |
| 3 | Jalankan beberapa worker (`uvicorn --workers N` / gunicorn) | Throughput naik mendekati ×N core |
| 4 | Tambah primary key ke `report_mauto_cdsbo`, ganti tiebreaker `ctid` | Paging stabil walau ada UPDATE |
| 5 | Index `(nik, apply_date)` saat volume data bertambah | Menjaga query tetap cepat |

## 6. Metode & lingkungan

- Kedua versi dijalankan dari git worktree terpisah, masing-masing **1 proses uvicorn** (sama seperti `main.py`),
  di server yang sama, berurutan (baseline 11:21–11:26, fix 11:28–11:33 WIB).
- Database: PostgreSQL dev/UAT `10.14.21.67` (sama untuk kedua run).
- Load generator: k6 0.54.0 (Docker `grafana/k6:0.54.0`, `--network host`), script `tests/k6/report_mauto_stress.js`.
- Server: 8 core, 62 GB RAM. k6 dan service berjalan di mesin yang sama, sehingga k6 juga memakai CPU.
- Functional test: `tests/functional` (pytest-bdd + Allure).

Reproduksi:

```bash
# service versi yang diuji harus sudah berjalan, contoh di port 8013
docker run --rm --network host -v "$PWD":/work -w /work -e API_KEY=<api-key> grafana/k6:0.54.0 \
  run -e SCENARIO=load -e DATA_FILE=./data.csv -e BASE_URL=http://localhost:8013 tests/k6/report_mauto_stress.js
REPORT_MAUTO_BASE_URL=http://localhost:8013 uv run pytest
```

## 7. File pendukung

| File | Isi |
|------|-----|
| `k6_load_baseline_main.txt` | Ringkasan k6 baseline (`main`) |
| `k6_load_fix.txt` | Ringkasan k6 versi fix |
| `resource_fix.csv` | CPU % dan RSS service versi fix, per 5 detik |
| `STRESS-BEFORE.md` | Stress test 20 → 300 VU sebelum perbaikan isu §9 (+ `k6_stress_before*.{txt,csv}`, `resource_stress_before.csv`) |
| `BASELINE-ISSUES.md` | Bukti isu README k6 §9 sebelum & sesudah perbaikan |
| `FIX-9.4.md` | Fix §9.4 (orjson, kontrak tetap) + stress test after (+ `k6_stress_after_fix94*`, `resource_stress_after_fix94.csv`) |
| `FIX-9.3.md` | Fix §9.3 logging (NIK & rotasi harian) |
| `FIX-9.1-9.2.md` | Fix §9.1/§9.2 pool, multi-worker, budget koneksi + stress 4 worker (+ `k6_stress_after_fix912*`, `resource_stress_after_fix912.csv`) |
