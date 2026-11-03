"""Step definitions untuk features/report_mauto.feature."""
import json
from collections import Counter

import allure
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

ENDPOINT = "/v1/report_mauto"

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
