"""Seed data sintetis untuk functional test di CI.

Membuat tabel (ci/schema.sql) lalu mengisi baris dummy yang memenuhi kebutuhan
features/report_mauto.feature. Tidak ada data asli; foto selfie/KTP diganti
string base64 pendek.

Koneksi diambil dari env POSTGRES_HOST/PORT/USER/PASSWORD/DB (sama dengan service).

    python tests/functional/ci/seed.py
"""
import base64
import os
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2

HERE = Path(__file__).resolve().parent

NIK_MAIN = "3201133107990002"
NIK_SECOND = "3204375008970013"
NIK_NOISE = "3201000000000099"  # nik lain di tanggal yang sama, harus tidak ikut terambil

# (nik, ddmmyyyy, jumlah baris). 29092025 dipakai TC-04..TC-12 (filter & paging),
# jadi dibuat 12 baris (> 2 halaman limit 5) dengan beberapa apply_date identik
# untuk menguji tiebreaker urutan paging.
COMBOS = [
    (NIK_MAIN, "29092025", 12),
    (NIK_MAIN, "12112025", 4),
    (NIK_MAIN, "09032026", 3),
    (NIK_MAIN, "31102025", 2),
    (NIK_MAIN, "27022026", 3),
    (NIK_MAIN, "30012026", 2),
    (NIK_MAIN, "02102025", 2),
    (NIK_MAIN, "13022026", 2),
    (NIK_SECOND, "24092026", 3),
]

CC_REFFS = ["CCR-A01", "CCR-A02", "CCR-B01", "CCR-B02"]
BRANCHES = ["101", "205"]
ACCOUNTS = ["1000000001", "1000000002", None]
STATUSES = ["APPROVED", "REJECTED", "PENDING"]
FAKE_IMAGE = base64.b64encode(b"dummy-image-for-ci" * 4).decode()


def _rows():
    seq = 0
    for nik, ddmmyyyy, count in COMBOS + [(NIK_NOISE, d, 2) for _, d, _ in COMBOS]:
        day = datetime.strptime(ddmmyyyy, "%d%m%Y")
        for i in range(count):
            seq += 1
            # tiap 3 baris berbagi timestamp yang sama -> apply_date tidak unik
            apply_at = day + timedelta(hours=9, minutes=(i // 3) * 15)
            yield {
                "application_id": f"APP-CI-{seq:05d}",
                "nik": nik,
                "apply_date": apply_at,
                "cc_reff": CC_REFFS[i % len(CC_REFFS)],
                "branch_code": BRANCHES[i % len(BRANCHES)],
                "account_number": ACCOUNTS[i % len(ACCOUNTS)],
                "status": STATUSES[i % len(STATUSES)],
                "nama_lengkap": f"NASABAH DUMMY {seq}",
                "product_code": "CC01",
                "inserted_at": apply_at,
                "inserted_by": "ci-seed",
                "selfie": FAKE_IMAGE,
                "request_base64_ktp": FAKE_IMAGE,
            }


def main():
    conn = psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ.get("POSTGRES_PORT", "5432"),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    )
    rows = list(_rows())
    cols = list(rows[0])
    sql = "INSERT INTO public.report_mauto_cdsbo ({}) VALUES ({})".format(
        ", ".join(f'"{c}"' for c in cols), ", ".join(["%s"] * len(cols))
    )
    with conn, conn.cursor() as cur:
        cur.execute((HERE / "schema.sql").read_text())
        cur.execute("TRUNCATE public.report_mauto_cdsbo")
        cur.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
    conn.close()
    print(f"seeded {len(rows)} rows")


if __name__ == "__main__":
    main()
