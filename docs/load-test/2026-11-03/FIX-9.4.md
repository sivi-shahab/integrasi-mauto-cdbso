# Fix §9.4: efisiensi response besar `POST /v1/report_mauto`

| Item | Nilai |
|------|-------|
| Isu | [README k6 §9.4](../../../tests/k6/README.md#94-ukuran-response): response besar karena 3 kolom gambar base64 |
| Keputusan | **Kontrak response tetap sama** (2026-11-03). Kolom `request_base64_ktp`, `profile_pic`, `selfie` tetap dikirim |
| Commit fix | `813e869` |
| Hasil | Throughput stress **28,55 → 70,25 req/s (2,46×)**, p95 **9,6 → 3,9 dtk**, response byte-identik |
| Bukti before | [STRESS-BEFORE.md](STRESS-BEFORE.md), [BASELINE-ISSUES.md](BASELINE-ISSUES.md#94-ukuran-response--tc-26-tc-27) |

## 1. Analisis penyebab

Karena kontrak tidak boleh berubah, yang bisa diperbaiki adalah **biaya CPU per byte**, bukan jumlah byte.
Waktu proses satu request 20 baris (13,8 MB) dari DB UAT diukur per tahap:

| Tahap | Waktu | Keterangan |
|-------|------:|------------|
| Query + fetch DB (psycopg2) | 54–89 ms | transfer 13,8 MB dari DB, tidak bisa dikurangi tanpa ubah kontrak |
| `dict(row)` | 0,8 ms | – |
| `jsonable_encoder` (FastAPI) | 13 ms | menelusuri 267 kolom × baris |
| **`json.dumps`** (Starlette `JSONResponse`) | **82–85 ms** | memindai string base64 besar |

Serialisasi (`jsonable_encoder` + `json.dumps`) memakan ±60% CPU per request. Service hanya punya 1 proses
yang CPU-nya jenuh (lihat STRESS-BEFORE §5), jadi biaya inilah yang membatasi throughput.

## 2. Perubahan

| File | Perubahan |
|------|-----------|
| `app/schemas/response.py` | `FastJSONResponse`: subclass `JSONResponse` yang me-render dengan `orjson.dumps` (tipe tak dikenal fallback ke `jsonable_encoder`) |
| `app/service/report_mauto_service.py` | Path sukses mengembalikan `FastJSONResponse(success_response(data))` langsung, sehingga FastAPI tidak menjalankan `jsonable_encoder` |
| `pyproject.toml`, `uv.lock`, `requirements.txt` | Dependency `orjson>=3.13.0` |
| `tests/functional/features/report_mauto.feature`, `test_report_mauto.py` | TC-26 & TC-27 disesuaikan dengan keputusan kontrak (lihat §4) |

Path error (`error_response`) tidak diubah. Ukurannya kecil dan tetap lewat jalur FastAPI biasa.

## 3. Verifikasi kontrak tidak berubah

1. **Serializer, seluruh data UAT:** 295 baris (dalam potongan 20 baris), output `orjson` dibandingkan dengan
   `JSONResponse(jsonable_encoder(...))`. Hasil: **0 perbedaan byte**. orjson menulis datetime naive dalam
   format ISO 8601 yang sama, UTF-8 tanpa escape, dan separator compact yang sama.
2. **End-to-end HTTP:** service lama (port 8921) dan baru (port 8922) dijalankan berdampingan terhadap DB UAT.
   Ada 17 request: 10 kombinasi data uji, paging, filter placeholder, data kosong, tanggal salah, nik placeholder,
   limit negatif, dan validasi 400. Status, body, `content-type`, dan `content-length`: **17/17 identik**.

   | Request | Ukuran | Lama | Baru |
   |---------|-------:|-----:|-----:|
   | nik …0002 / 29092025 (20 baris) | 13,83 MB | 174 ms | 93 ms |
   | nik …0002 / 02102025 | 5,70 MB | 79 ms | 40 ms |
   | nik …0002 / 27022026 | 3,31 MB | 54 ms | 29 ms |
   | nik …0013 / 24092026 | 2,74 MB | 49 ms | 31 ms |
   | nik …0002 / 29092025 limit 5 offset 5 | 4,63 MB | 53 ms | 32 ms |
   | request kecil / error | < 1 kB | 2–10 ms | 3–10 ms |

3. **Functional test:** semua TC-01 sampai TC-21 tetap lulus. TC-02 (field utama) dan TC-26 (kolom gambar &
   format `apply_date`) menjadi guard kontrak.

## 4. Test case Allure (TS-08)

Definisi awal TC-26/TC-27 (capture before) mengasumsikan kolom gambar dihapus dari response. Karena keputusannya
kontrak tetap, keduanya diganti agar mengukur hal yang benar:

| TC | Sebelum keputusan | Sekarang | Kode lama | Kode baru |
|----|-------------------|----------|-----------|-----------|
| TC-26 | tidak ada kolom gambar | **guard kontrak**: kolom gambar tetap ada, `apply_date` ISO 8601 | lulus | lulus |
| TC-27 | < 20 KB per baris | **render endpoint** 12 baris (6,8 MB, ukuran gambar = rata-rata UAT) dengan DB palsu, median < 35 ms | **gagal: 52–56 ms** | **lulus: ±17 ms** |

TC-27 memakai `TestClient` + DB palsu di proses terpisah, sehingga yang terukur hanya biaya aplikasi
(validasi, service, serialisasi), tanpa DB dan jaringan. Batas 35 ms memberi margin untuk runner CI yang
lebih lambat. Keduanya tanpa tag `@known_issue`, jadi menjadi gate.

Riwayat Allure untuk TC-26/TC-27 dimulai ulang karena judul skenarionya berubah. Bukti gagal versi awal
tetap tercatat di [BASELINE-ISSUES.md](BASELINE-ISSUES.md) dan run GitHub Actions `41611205164`.

## 5. Stress test: before vs after

Konfigurasi identik dengan [STRESS-BEFORE.md §2](STRESS-BEFORE.md#2-lingkungan--konfigurasi): server yang sama,
1 proses uvicorn port 8915, DB UAT, `tests/k6/data.csv` (10 kombinasi), skenario `stress`, k6 0.54.0 Docker.
After dijalankan 2026-11-03 17:56:52 – 18:07:57 WIB pada commit `813e869`.

| Metrik | Before (`146601d`) | After (`813e869`) | Perubahan |
|--------|-------------------:|------------------:|----------:|
| Total request (11 menit) | 18.849 | 46.372 | +146% |
| **Throughput** | **28,55 req/s** | **70,25 req/s** | **×2,46** |
| Latency avg | 4.237 ms | 1.690 ms | −60% |
| Latency p50 | 3.338 ms | 1.436 ms | −57% |
| **Latency p95** | **9.602 ms** | **3.913 ms** | **−59%** |
| Latency p99 | 10.213 ms | 4.291 ms | −58% |
| Latency max | 11.921 ms | 5.275 ms | −56% |
| HTTP gagal / business gagal | 0% / 0% | 0% / 0% | – |
| Data diterima | 63,3 GB (98,2 MB/s) | 155,1 GB (240,6 MB/s) | ×2,45 |
| Ukuran rata-rata response | 3,6 MB | 3,6 MB | sama (kontrak tetap) |
| CPU service | ±110% | ±123% | – |
| RSS maks | 1.991 MB | 1.919 MB | ≈ sama |
| Threshold p95 < 1 dtk / p99 < 2 dtk | ✗ / ✗ | ✗ / ✗ | masih gagal pada 300 VU |

Per tahap VU (RPS · p95):

| Tahap | VU | Before | After |
|-------|---:|-------:|------:|
| 0 → 20 | 19 | 24,5 req/s · 758 ms | 56,8 req/s · 270 ms |
| 20 → 50 | 49 | 28,6 · 1.687 ms | 69,8 · 726 ms |
| 50 → 100 | 99 | 29,9 · 3.402 ms | 69,5 · 1.503 ms |
| 100 → 200 | 199 | 28,9 · 7.017 ms | 73,0 · 2.676 ms |
| 200 → 300 | 299 | 28,9 · 9.878 ms | 72,7 · 4.132 ms |
| 300 → 0 (recovery) | 300 | 28,6 · 10.187 ms | 73,0 · 4.220 ms |

Per 30 detik: [`k6_stress_before_timeline.csv`](k6_stress_before_timeline.csv) vs
[`k6_stress_after_fix94_timeline.csv`](k6_stress_after_fix94_timeline.csv).

**Kapasitas yang memenuhi p95 < 1 dtk:** before ±20–25 VU / ±28 req/s → after **±55 VU / ±70 req/s**
(p95 828 ms pada 49 VU, 1.042 ms pada 62 VU). Service tetap pulih penuh setelah beban turun (87 ms pada 1 VU).

## 6. Interpretasi & batasan

- Peningkatan sepenuhnya berasal dari serialisasi. Kode lain dan isi response tidak berubah.
- Throughput tetap mentok (sekarang ±73 req/s) karena CPU 1 proses masih jenuh. Langkah berikutnya: multi-worker (P2).
- **Bandwidth naik ×2,45 (240 MB/s ≈ 1,9 Gbit/s).** Di test ini k6 berada di mesin yang sama (loopback). Pada
  jaringan nyata 1 Gbit, batas jaringan (±120 MB/s ≈ 33 req/s × 3,6 MB) bisa tercapai lebih dulu dari CPU.
  Ini konsekuensi keputusan kontrak tetap, dan perlu dicatat saat P2 (**perkiraan**, belum diukur di jaringan nyata).
- Memori per proses tetap ±2 GB pada 300 VU. Multi-worker akan melipatgandakan kebutuhan RAM.
- Keterbatasan sama dengan STRESS-BEFORE §7: k6 di mesin yang sama, server bersama, data uji 10 kombinasi, 1 run.
  Pada ±2 menit terakhir run after, ada pengecekan ringan logging (§9.3, proses Python singkat) di server yang sama.

## 7. File

| File | Isi |
|------|-----|
| [`k6_stress_after_fix94.txt`](k6_stress_after_fix94.txt) | Ringkasan k6 after |
| [`k6_stress_after_fix94_timeline.csv`](k6_stress_after_fix94_timeline.csv) | RPS & latency per 30 detik |
| [`resource_stress_after_fix94.csv`](resource_stress_after_fix94.csv) | CPU % & RSS service per 5 detik |
| `tests/k6/published/after/summary_stress_20261103_110753.{json,txt}` | Allure TS-07 `stress · Internal UAT · after fix` |
