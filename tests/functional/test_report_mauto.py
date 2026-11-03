"""Step definitions untuk features/report_mauto.feature."""
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import allure
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

ENDPOINT = "/v1/report_mauto"
ROOT = Path(__file__).resolve().parents[2]
# Folder log service (service dijalankan dari root project -> logs/).
LOG_DIR = Path(os.getenv("REPORT_MAUTO_LOG_DIR", ROOT / "logs"))

scenarios("features/report_mauto.feature")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _send(client, ctx, payload):
    """Kirim request dan simpan hasilnya ke ctx.

    Body response TIDAK dilampirkan utuh ke report: berisi data pribadi nasabah
    serta foto selfie/KTP base64 (bisa >10 MB). Yang dilampirkan hanya ringkasan.
    """
    allure.attach(json.dumps(payload, indent=2), "request body", allure.attachment_type.JSON)
    resp = client.post(ENDPOINT, json=payload, headers=ctx["headers"])
    try:
        body = resp.json()
    except ValueError:
        body = None
    ctx.update(resp=resp, body=body)

    data = body.get("data") if isinstance(body, dict) else None
    summary = {
        "http_status": resp.status_code,
        "responseCode": body.get("responseCode") if isinstance(body, dict) else None,
        "responseDescription": (body.get("responseDescription") or body.get("detail"))
        if isinstance(body, dict) else resp.text[:300],
        "row_count": len(data) if isinstance(data, list) else None,
        "size_kb": round(len(resp.content) / 1024, 1),
        "elapsed_ms": round(resp.elapsed.total_seconds() * 1000, 1),
        "rows": [
            {k: r.get(k) for k in ("application_id", "apply_date", "status")}
            for r in (data or [])
        ],
    }
    allure.attach(json.dumps(summary, indent=2, default=str), "response summary",
                  allure.attachment_type.JSON)
    return body


def _rows(ctx):
    body = ctx["body"]
    assert isinstance(body, dict), f"Response bukan JSON object: {ctx['resp'].text[:300]}"
    return body.get("data") or []


def _canon(row):
    return json.dumps(row, sort_keys=True, default=str)


def _to_iso(ddmmyyyy):
    return f"{ddmmyyyy[4:]}-{ddmmyyyy[2:4]}-{ddmmyyyy[:2]}"


def _inspect(code, env=None, cwd=ROOT, args=()):
    """Jalankan potongan Python di proses terpisah (pakai kode service) dan kembalikan JSON-nya.

    Proses terpisah agar env override dan side effect (mis. setup_logging) tidak
    memengaruhi proses test.
    """
    full_env = {**os.environ, "PYTHONPATH": str(ROOT), **(env or {})}
    proc = subprocess.run([sys.executable, "-c", code, *args], cwd=cwd, env=full_env,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"Inspeksi gagal: {proc.stderr[-1000:]}"
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    allure.attach(json.dumps(result, indent=2), "konfigurasi service", allure.attachment_type.JSON)
    return result


_POOL_CODE = """
import json
from app.db.session import engine
p = engine.pool
print(json.dumps({"pool_class": type(p).__name__, "pool_size": p.size(),
    "max_overflow": getattr(p, "_max_overflow", None), "pool_timeout": getattr(p, "_timeout", None),
    "pool_pre_ping": bool(getattr(p, "_pre_ping", False)), "pool_recycle": getattr(p, "_recycle", None)}))
"""

_LOG_ERROR_CODE = """
import json, logging, pathlib, sys
from app.core.logging import setup_logging
setup_logging()
log = logging.getLogger("app.service.report_mauto_service")
nik = sys.argv[1]
try:
    raise RuntimeError(f"query gagal [parameters: {{'nik': '{nik}'}}]")
except RuntimeError:
    log.exception("get_report_mauto failed, nik=%s", nik)
log.error(f"Exception: nik={nik}")
for h in logging.getLogger().handlers:
    h.flush()
text = "".join(p.read_text(encoding="utf-8") for p in pathlib.Path("logs").glob("*.log*"))
print(json.dumps({"log": text}))
"""

_BUDGET_CODE = """
import json, sys
try:
    from app.db.session import check_connection_budget
except ImportError as exc:
    print(json.dumps({"supported": False, "error": str(exc)}))
    raise SystemExit
out = {"supported": True}
for workers in map(int, sys.argv[1:]):
    try:
        out[workers] = {"accepted": True, "total": check_connection_budget(workers)}
    except ValueError as exc:
        out[workers] = {"accepted": False, "error": str(exc)}
print(json.dumps(out))
"""

# Dua "worker" = dua set handler (setup_logging dua kali) yang menulis file yang sama
# dengan stream masing-masing, persis seperti dua proses uvicorn. Rotasi dipaksa pada
# keduanya (meniru tengah malam); tanggal digeser +1 hari untuk handler berbasis tanggal.
_MULTI_ROTATE_CODE = """
import datetime as dt, json, logging, logging.handlers, pathlib
import app.core.logging as L
L.setup_logging(); L.setup_logging()
log = logging.getLogger("multi")
log.warning("MARK-HARI-1")
class NextDay(dt.date):
    @classmethod
    def today(cls):
        return dt.date.today() + dt.timedelta(days=1)
L.date = NextDay
handlers = [h for h in logging.getLogger().handlers if isinstance(h, logging.handlers.BaseRotatingHandler)]
for h in handlers:
    h.doRollover()
log.warning("MARK-HARI-2")
for h in handlers:
    h.flush()
texts = {p.name: p.read_text(encoding="utf-8") for p in pathlib.Path("logs").iterdir()}
# file aktif (hari baru) menurut handler detailed; log hari-2 harus masuk ke sana
active = sorted({pathlib.Path(h.baseFilename).name for h in handlers if "detailed" in h.baseFilename})
print(json.dumps({"workers": 2, "files": sorted(texts), "active_files": active,
    "hari1": sum(t.count("MARK-HARI-1") for t in texts.values()),
    "hari2": sum(t.count("MARK-HARI-2") for t in texts.values()),
    "hari2_di_file_aktif": sum(texts.get(a, "").count("MARK-HARI-2") for a in active),
    "per_file": {n: {"hari1": t.count("MARK-HARI-1"), "hari2": t.count("MARK-HARI-2")} for n, t in texts.items()}}))
"""

_LOGGING_CODE = """
import json, logging, logging.handlers
from app.core.logging import setup_logging
setup_logging()
print(json.dumps([{"handler": type(h).__name__, "file": getattr(h, "baseFilename", None),
    "timed": isinstance(h, logging.handlers.TimedRotatingFileHandler),
    "when": getattr(h, "when", None)} for h in logging.getLogger().handlers]))
"""


# Benchmark jalur endpoint lengkap (validasi, service, serialisasi) memakai
# TestClient dan DB palsu, sehingga hanya biaya aplikasi yang terukur (tanpa DB/jaringan).
# Ukuran kolom gambar = rata-rata UAT 2026-11-03.
_BENCH_CODE = """
import base64, datetime, json, logging, statistics, time
logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from main import app
from app.core.configs import settings
from app.core.deps import get_db

def img(kb):
    raw = (b"dummy-image-for-ci-" * (kb * 1024 // 19 + 1))[: kb * 1024 * 3 // 4]
    return base64.b64encode(raw).decode()

rows = [{"application_id": f"APP-{i}", "nik": "3201133107990002",
         "apply_date": datetime.datetime(2025, 9, 29, 9, i), "status": "APPROVED",
         "selfie": img(50), "profile_pic": img(131), "request_base64_ktp": img(375)} for i in range(12)]

class _Result:
    def mappings(self): return self
    def all(self): return rows

class FakeDB:
    def execute(self, *a, **k): return _Result()
    def close(self): pass

app.dependency_overrides[get_db] = lambda: FakeDB()
client = TestClient(app)
headers = {settings.API_KEY_NAME: settings.VALID_API_KEYS}
times = []
for _ in range(9):
    t = time.perf_counter()
    r = client.post("/v1/report_mauto", json={"nik": "3201133107990002", "apply_date": "29092025"}, headers=headers)
    times.append((time.perf_counter() - t) * 1000)
assert r.status_code == 200 and r.json()["responseCode"] == "00", r.text[:200]
print(json.dumps({"rows": len(rows), "response_mb": round(len(r.content) / 1e6, 2),
                  "median_ms": round(statistics.median(times[2:]), 1), "runs_ms": [round(x, 1) for x in times]}))
"""


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------
@given("service report_mauto tersedia")
def service_available(client):
    try:
        client.get("/docs")
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"Service tidak dapat dihubungi di {client.base_url}: {exc}")


@given(parsers.parse('API key yang digunakan "{key}"'))
def use_api_key(ctx, key, api_key, api_key_name):
    ctx["headers"].pop(api_key_name, None)
    if key == "valid":
        ctx["headers"][api_key_name] = api_key.value
    elif key == "salah":
        ctx["headers"][api_key_name] = "invalid-api-key-for-test"
    elif key == "kosong":
        ctx["headers"][api_key_name] = ""
    elif key == "tanpa":
        pass  # header tidak dikirim
    else:
        raise ValueError(f"Jenis API key tidak dikenal: {key}")


@given(parsers.parse('data acuan untuk nik "{nik}" dan apply_date "{apply_date}"'))
def reference_data(client, ctx, nik, apply_date):
    with allure.step("Ambil data acuan tanpa filter (limit 1000)"):
        body = _send(client, ctx, {"nik": nik, "apply_date": apply_date, "limit": 1000, "offset": 0})
    assert body and body.get("responseCode") == "00", f"Data acuan gagal diambil: {body and body.get('responseDescription')}"
    assert body["data"], "Data acuan kosong, test tidak dapat dijalankan"
    ctx.update(ref=body["data"], ref_nik=nik, ref_date=apply_date)


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------
@when(parsers.parse('request dikirim dengan nik "{nik}" dan apply_date "{apply_date}"'))
def send_nik_date(client, ctx, nik, apply_date):
    _send(client, ctx, {"nik": nik, "apply_date": apply_date, "limit": 100, "offset": 0})


@when(parsers.parse("request dikirim dengan body {body}"))
def send_body(client, ctx, body):
    _send(client, ctx, json.loads(body))


@when(parsers.parse("request dikirim dengan filter {field} dari baris acuan"))
def send_with_filter(client, ctx, field):
    row = next((r for r in ctx["ref"] if r.get(field) not in (None, "")), None)
    if row is None:
        pytest.skip(f"Tidak ada baris acuan dengan {field} terisi")
    ctx["filter"] = (field, str(row[field]))
    _send(client, ctx, {
        "nik": ctx["ref_nik"], "apply_date": ctx["ref_date"],
        field: str(row[field]), "limit": 1000, "offset": 0,
    })


@when(parsers.parse("seluruh halaman diambil dengan limit {limit:d}"))
def fetch_all_pages(client, ctx, limit):
    pages, offset = [], 0
    while True:
        with allure.step(f"Ambil halaman offset={offset} limit={limit}"):
            body = _send(client, ctx, {
                "nik": ctx["ref_nik"], "apply_date": ctx["ref_date"],
                "limit": limit, "offset": offset,
            })
        assert body.get("responseCode") == "00", body.get("responseDescription")
        page = body.get("data") or []
        pages.append(page)
        if len(page) < limit or offset > len(ctx["ref"]) + limit:
            break
        offset += limit
    ctx["pages"] = pages


@when("konfigurasi pool database service dibaca")
def read_pool_config(ctx):
    ctx["pool"] = _inspect(_POOL_CODE)


@when(parsers.parse('konfigurasi pool database service dibaca dengan env "{pairs}"'))
def read_pool_config_env(ctx, pairs):
    env = dict(p.split("=", 1) for p in pairs.split(","))
    ctx["pool"] = _inspect(_POOL_CODE, env=env)


@when(parsers.parse('batas koneksi diperiksa untuk {a:d} dan {b:d} worker dengan env "{pairs}"'))
def check_budget(ctx, a, b, pairs):
    env = dict(p.split("=", 1) for p in pairs.split(","))
    ctx["budget"] = _inspect(_BUDGET_CODE, env=env, args=(str(a), str(b)))


@when("dua worker menulis log lalu sama-sama melakukan rotasi tengah malam")
def multi_worker_rotate(ctx):
    with tempfile.TemporaryDirectory() as tmp:
        ctx["rotation"] = _inspect(_MULTI_ROTATE_CODE, cwd=tmp)


@when("konfigurasi logging service dibaca")
def read_logging_config(ctx):
    with tempfile.TemporaryDirectory() as tmp:  # setup_logging membuat folder logs/ di cwd
        ctx["log_handlers"] = _inspect(_LOGGING_CODE, cwd=tmp)


@when("response 12 baris dengan kolom gambar seukuran UAT dirender lewat endpoint")
def bench_render(ctx):
    ctx["bench"] = _inspect(_BENCH_CODE)


@when(parsers.parse('error yang memuat nik "{nik}" dicatat oleh logging service'))
def log_error_with_nik(ctx, nik):
    with tempfile.TemporaryDirectory() as tmp:  # file log ditulis ke tmp/logs
        ctx["error_log"] = _inspect(_LOG_ERROR_CODE, cwd=tmp, args=(nik,))["log"]


@when(parsers.parse('request dikirim sambil memantau log service dengan nik "{nik}" dan apply_date "{apply_date}"'))
def send_and_watch_log(client, ctx, nik, apply_date):
    if not LOG_DIR.is_dir():
        pytest.skip(f"Folder log service tidak ditemukan ({LOG_DIR}); set REPORT_MAUTO_LOG_DIR")
    before = {f: f.stat().st_size for f in LOG_DIR.glob("*.log")}
    _send(client, ctx, {"nik": nik, "apply_date": apply_date, "limit": 100, "offset": 0})
    time.sleep(0.5)  # beri waktu handler menulis ke file
    new_lines = []
    for f in LOG_DIR.glob("*.log"):
        with f.open("rb") as fh:
            fh.seek(before.get(f, 0))
            new_lines += fh.read().decode("utf-8", "replace").splitlines()
    ctx["log_lines"] = new_lines


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------
@then(parsers.parse("HTTP status adalah {status:d}"))
def check_status(ctx, status):
    assert ctx["resp"].status_code == status, (
        f"HTTP {ctx['resp'].status_code}, diharapkan {status}. Body: {ctx['resp'].text[:300]}"
    )


@then(parsers.parse('responseCode adalah "{code}"'))
def check_response_code(ctx, code):
    body = ctx["body"]
    assert isinstance(body, dict), f"Response bukan JSON: {ctx['resp'].text[:300]}"
    assert body.get("responseCode") == code, (
        f"responseCode={body.get('responseCode')!r} ({body.get('responseDescription')}), diharapkan {code!r}"
    )


@then(parsers.parse('responseDescription mengandung "{text}"'))
def check_description(ctx, text):
    desc = str(ctx["body"].get("responseDescription"))
    assert text in desc, f"responseDescription={desc!r} tidak mengandung {text!r}"


@then("data tidak kosong")
def data_not_empty(ctx):
    assert len(_rows(ctx)) > 0, "data kosong"


@then("data kosong")
def data_empty(ctx):
    assert not _rows(ctx), f"data berisi {len(_rows(ctx))} baris, diharapkan kosong"


@then(parsers.parse("jumlah baris adalah {n:d}"))
def row_count_is(ctx, n):
    assert len(_rows(ctx)) == n, f"jumlah baris {len(_rows(ctx))}, diharapkan {n}"


@then("jumlah baris sama dengan data acuan")
def row_count_equals_ref(ctx):
    assert len(_rows(ctx)) == len(ctx["ref"]), f"{len(_rows(ctx))} baris, data acuan {len(ctx['ref'])}"


@then("jumlah baris tidak lebih dari data acuan")
def row_count_le_ref(ctx):
    assert len(_rows(ctx)) <= len(ctx["ref"])


@then(parsers.parse('semua baris memiliki nik "{nik}"'))
def all_rows_nik(ctx, nik):
    wrong = [r.get("nik") for r in _rows(ctx) if str(r.get("nik")) != nik]
    assert not wrong, f"{len(wrong)} baris dengan nik berbeda: {sorted(set(wrong))[:5]}"


@then(parsers.parse('semua baris memiliki apply_date pada tanggal "{apply_date}"'))
def all_rows_date(ctx, apply_date):
    iso = _to_iso(apply_date)
    wrong = [r.get("apply_date") for r in _rows(ctx) if not str(r.get("apply_date", "")).startswith(iso)]
    assert not wrong, f"{len(wrong)} baris di luar tanggal {iso}: {wrong[:5]}"


@then("baris terurut berdasarkan apply_date secara ascending")
def rows_sorted(ctx):
    dates = [str(r.get("apply_date")) for r in _rows(ctx)]
    assert dates == sorted(dates), f"apply_date tidak terurut: {dates}"


@then(parsers.parse("waktu respons di bawah {ms:d} ms"))
def response_time(ctx, ms):
    elapsed = ctx["resp"].elapsed.total_seconds() * 1000
    assert elapsed < ms, f"waktu respons {elapsed:.0f} ms >= {ms} ms"


@then(parsers.parse('setiap baris memuat field "{fields}"'))
def rows_have_fields(ctx, fields):
    required = [f.strip() for f in fields.split(",")]
    rows = _rows(ctx)
    assert rows, "data kosong"
    missing = sorted({f for r in rows for f in required if f not in r})
    assert not missing, f"field tidak ada di response: {missing}"


@then(parsers.parse("semua baris memiliki {field} sama dengan baris acuan"))
def rows_match_filter(ctx, field):
    f, value = ctx["filter"]
    assert f == field
    wrong = [r.get(field) for r in _rows(ctx) if str(r.get(field)) != value]
    assert not wrong, f"{len(wrong)} baris dengan {field} != {value}: {wrong[:5]}"


@then("gabungan semua halaman sama persis dengan data acuan")
def pages_match_ref(ctx):
    combined = [r for p in ctx["pages"] for r in p]
    got, want = Counter(map(_canon, combined)), Counter(map(_canon, ctx["ref"]))
    duplicated = sum((got - want).values())
    missing = sum((want - got).values())
    allure.attach(
        json.dumps({"pages": [len(p) for p in ctx["pages"]], "total_paged": len(combined),
                    "total_reference": len(ctx["ref"]), "duplicated_rows": duplicated,
                    "missing_rows": missing}, indent=2),
        "paging check", allure.attachment_type.JSON,
    )
    assert duplicated == 0 and missing == 0, (
        f"Paging tidak konsisten: {duplicated} baris muncul ganda, {missing} baris hilang "
        f"(total paging {len(combined)} vs acuan {len(ctx['ref'])}). "
        "Kemungkinan ORDER BY apply_date tidak unik sehingga urutan antar halaman tidak stabil."
    )


# --- TS-08 isu README k6 §9 ---
@then("pool_pre_ping aktif")
def pool_pre_ping(ctx):
    assert ctx["pool"]["pool_pre_ping"], "pool_pre_ping=False: koneksi mati tidak dideteksi sebelum dipakai"


@then(parsers.parse("pool_timeout tidak lebih dari {sec:d} detik"))
def pool_timeout(ctx, sec):
    t = ctx["pool"]["pool_timeout"]
    assert t is not None and t <= sec, (
        f"pool_timeout={t} detik (> {sec}): saat pool habis request menunggu lama lalu responseCode 99"
    )


@then(parsers.parse("pool_size adalah {n:d}"))
def pool_size_is(ctx, n):
    assert ctx["pool"]["pool_size"] == n, (
        f"pool_size={ctx['pool']['pool_size']}, diharapkan {n} dari env DB_POOL_SIZE (belum bisa dikonfigurasi)"
    )


@then(parsers.parse("max_overflow adalah {n:d}"))
def max_overflow_is(ctx, n):
    assert ctx["pool"]["max_overflow"] == n, (
        f"max_overflow={ctx['pool']['max_overflow']}, diharapkan {n} dari env DB_MAX_OVERFLOW"
    )


def _mask_nik(text, nik):
    return text.replace(nik, nik[:4] + "*" * (len(nik) - 8) + nik[-4:])


@then(parsers.parse('log service level INFO tidak memuat nik "{nik}"'))
def log_has_no_nik(ctx, nik):
    lines = ctx["log_lines"]
    leaked = [_mask_nik(line, nik) for line in lines if " INFO " in line and nik in line]
    allure.attach(
        json.dumps({"log_lines_baru": len(lines), "baris_info_berisi_nik": len(leaked),
                    "contoh (nik disamarkan)": leaked[:3]}, indent=2),
        "log service", allure.attachment_type.JSON,
    )
    assert not leaked, f"{len(leaked)} baris log INFO memuat NIK, contoh: {leaked[0]}"


@then(parsers.parse('log service tidak memuat nik "{nik}" pada level apa pun'))
def log_has_no_nik_any_level(ctx, nik):
    leaked = [_mask_nik(line, nik) for line in ctx["log_lines"] if nik in line]
    assert not leaked, f"{len(leaked)} baris log memuat NIK lengkap, contoh: {leaked[0]}"


@then(parsers.parse('file log tidak memuat nik "{nik}"'))
def error_log_no_nik(ctx, nik):
    text = ctx["error_log"]
    allure.attach(_mask_nik(text, nik)[-3000:], "isi file log (NIK disamarkan untuk report)",
                  allure.attachment_type.TEXT)
    count = text.count(nik)
    assert count == 0, f"NIK lengkap muncul {count} kali di file log (pesan error/traceback)"


@then(parsers.parse('file log memuat nik tersamar "{masked}"'))
def error_log_masked(ctx, masked):
    assert masked in ctx["error_log"], f"NIK tersamar {masked!r} tidak ditemukan di file log"


@then("file log memakai rotasi harian")
def log_rotates_daily(ctx):
    file_handlers = [h for h in ctx["log_handlers"] if h["file"]]
    assert file_handlers, "Tidak ada file handler"
    wrong = [h for h in file_handlers if not h.get("timed") or h["when"] != "MIDNIGHT"]
    assert not wrong, (
        "File log tidak dirotasi harian: "
        + ", ".join(f"{h['handler']} ({Path(h['file']).name})" for h in wrong)
        + ". Nama file memakai tanggal saat service start, sehingga log berhari-hari masuk satu file."
    )


@then(parsers.parse('apply_date dalam format ISO 8601 "{fmt}"'))
def apply_date_iso(ctx, fmt):
    import re
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$")
    wrong = [r.get("apply_date") for r in _rows(ctx) if not pattern.match(str(r.get("apply_date")))]
    assert not wrong, f"apply_date tidak sesuai format {fmt}: {wrong[:3]}"


@then(parsers.parse("waktu render median di bawah {ms:d} ms"))
def render_time(ctx, ms):
    b = ctx["bench"]
    assert b["median_ms"] < ms, (
        f"render {b['response_mb']} MB ({b['rows']} baris) median {b['median_ms']} ms >= {ms} ms "
        "(serialisasi JSON standar: jsonable_encoder + json.dumps)"
    )


@then(parsers.parse("konfigurasi {workers:d} worker diterima dengan total {total:d} koneksi"))
def budget_accepted(ctx, workers, total):
    b = ctx["budget"]
    assert b["supported"], f"Batas total koneksi belum diterapkan: {b.get('error')}"
    r = b[str(workers)]
    assert r["accepted"] and r["total"] == total, f"{workers} worker: {r}"


@then(parsers.parse("konfigurasi {workers:d} worker ditolak karena melebihi DB_CONNECTION_BUDGET"))
def budget_rejected(ctx, workers):
    b = ctx["budget"]
    assert b["supported"], f"Batas total koneksi belum diterapkan: {b.get('error')}"
    r = b[str(workers)]
    assert not r["accepted"] and "DB_CONNECTION_BUDGET" in r["error"], f"{workers} worker seharusnya ditolak: {r}"


@then("semua baris log sebelum dan sesudah rotasi masih tersimpan")
def rotation_no_loss(ctx):
    r = ctx["rotation"]
    expected = r["workers"]
    assert r["hari1"] == expected and r["hari2"] == expected, (
        f"Log hilang saat rotasi multi-worker: sebelum rotasi {r['hari1']}/{expected} baris, "
        f"sesudah rotasi {r['hari2']}/{expected} baris. File: {r['files']}"
    )


@then("log setelah rotasi dari semua worker masuk ke file hari baru")
def rotation_new_file(ctx):
    r = ctx["rotation"]
    assert r["hari2_di_file_aktif"] == r["workers"], (
        f"Hanya {r['hari2_di_file_aktif']}/{r['workers']} worker menulis ke file hari baru {r['active_files']}; "
        f"worker lain masih menulis ke file hari sebelumnya. Sebaran: {r['per_file']}"
    )
