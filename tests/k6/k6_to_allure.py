#!/usr/bin/env python3
"""Konversi summary k6 (output handleSummary report_mauto_stress.js) ke Allure results.

Setiap threshold k6 menjadi satu test case Allure di bawah story
"TS-07 Performa (k6)", sehingga hasil smoke/load/stress tampil di report yang
sama dengan functional test BDD.

    python tests/k6/k6_to_allure.py tests/k6/results/summary_*.json \
        --out tests/functional/allure-results --env "CI (GitHub Actions)"

    # folder: hanya summary terbaru per skenario yang diambil
    python tests/k6/k6_to_allure.py tests/k6/published --out ... --env "Internal UAT"

Hanya memakai standard library.
"""
import argparse
import hashlib
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

EPIC = "Report Mauto CDSBO"
FEATURE = "POST /v1/report_mauto"
STORY = "TS-07 Performa (k6)"

# (metric, threshold expr) -> (TC id, judul, severity)
KNOWN = {
    ("http_req_failed", "rate<0.01"): ("TC-17", "Error HTTP di bawah 1%", "critical"),
    ("http_req_duration", "p(95)<1000"): ("TC-18", "Latency p95 di bawah 1000 ms", "critical"),
    ("http_req_duration", "p(99)<2000"): ("TC-19", "Latency p99 di bawah 2000 ms", "normal"),
    ("business_success", "rate>0.99"): ("TC-20", "responseCode 00 di atas 99%", "critical"),
    ("checks", "rate>0.99"): ("TC-21", "Check k6 lulus di atas 99%", "normal"),
}

_EXPR = re.compile(r"^\s*([a-z]+(?:\(\d+(?:\.\d+)?\))?)\s*(<=|>=|<|>|==|!=)\s*([\d.]+)\s*$")
_URL_HOST = re.compile(r"(https?://)[^/\s]+")


def mask_host(text):
    """Samarkan host/IP target (repo publik)."""
    return _URL_HOST.sub(r"\1<host>", text)


def actual_value(metric, expr):
    m = _EXPR.match(expr)
    if not m:
        return None, expr
    key = m.group(1)
    value = metric.get("values", {}).get(key)
    if value is None:
        return None, expr
    if key == "rate":
        shown = f"{value * 100:.2f}%"
    elif metric.get("contains") == "time":
        shown = f"{value:.1f} ms"
    else:
        shown = f"{value:g}"
    return value, f"{key} = {shown} (threshold {expr})"


def overview(summary):
    """Ringkasan metrik utama untuk lampiran."""
    m = summary.get("metrics", {})
    get = lambda name, key: m.get(name, {}).get("values", {}).get(key)  # noqa: E731
    dur = m.get("http_req_duration", {}).get("values", {})
    reqs = get("http_reqs", "count") or 0
    received = get("data_received", "count") or 0
    return {
        "scenario": summary.get("meta", {}).get("scenario"),
        "duration_s": round((summary.get("state", {}).get("testRunDurationMs") or 0) / 1000, 1),
        "vus_max": get("vus_max", "max"),
        "http_reqs": reqs,
        "rps": round(get("http_reqs", "rate") or 0, 2),
        "latency_ms": {k: round(v, 1) for k, v in dur.items()},
        "http_req_failed_pct": round((get("http_req_failed", "rate") or 0) * 100, 2),
        "business_success_pct": round((get("business_success", "rate") or 0) * 100, 2),
        "avg_response_kb": round(received / reqs / 1024, 1) if reqs else None,
        "rows_returned_avg": round(get("rows_returned", "avg") or 0, 2),
    }


def pick_files(inputs):
    """File diambil apa adanya; folder -> summary terbaru per skenario."""
    files = []
    for p in map(Path, inputs):
        if p.is_dir():
            latest = {}
            for f in sorted(p.glob("summary_*.json")):  # nama mengandung timestamp, sort = urut waktu
                scenario = f.stem.split("_")[1]
                latest[scenario] = f
            files.extend(latest.values())
        elif p.is_file():
            files.append(p)
    return files


def write_attachment(out, content, name, mime, ext):
    source = f"{uuid.uuid4()}-attachment.{ext}"
    (out / source).write_text(content, encoding="utf-8")
    return {"name": name, "source": source, "type": mime}


def convert(path, out, env):
    summary = json.loads(path.read_text(encoding="utf-8"))
    meta = summary.get("meta", {})
    scenario = meta.get("scenario", "unknown")
    finished = datetime.fromisoformat(meta["finished_at"].replace("Z", "+00:00")) if meta.get("finished_at") else datetime.now()
    stop = int(finished.timestamp() * 1000)
    start = stop - int(summary.get("state", {}).get("testRunDurationMs") or 0)

    txt_path = path.with_suffix(".txt")
    txt = mask_host(txt_path.read_text(encoding="utf-8")) if txt_path.exists() else None
    ov = json.dumps(overview(summary), indent=2)

    count = 0
    for name, metric in summary.get("metrics", {}).items():
        for expr, result in (metric.get("thresholds") or {}).items():
            tc, title, severity = KNOWN.get((name, expr), (None, f"{name} {expr}", "normal"))
            _, detail = actual_value(metric, expr)
            ok = bool(result.get("ok"))
            full_name = f"{tc + ' ' if tc else ''}{title} [{scenario} · {env}]"
            history_key = f"k6|{env}|{scenario}|{name}|{expr}"

            attachments = [write_attachment(out, ov, "k6 overview", "application/json", "json")]
            if txt:
                attachments.append(write_attachment(out, txt, "k6 summary", "text/plain", "txt"))

            labels = [
                {"name": "epic", "value": EPIC},
                {"name": "feature", "value": FEATURE},
                {"name": "story", "value": STORY},
                {"name": "severity", "value": severity},
                {"name": "tag", "value": f"k6:{scenario}"},
                {"name": "tag", "value": env},
                {"name": "framework", "value": "k6"},
                {"name": "suite", "value": f"k6 {scenario}"},
            ]
            if tc:
                labels += [{"name": "tag", "value": tc}, {"name": "as_id", "value": tc}]

            result_json = {
                "uuid": str(uuid.uuid4()),
                "historyId": hashlib.md5(history_key.encode()).hexdigest(),
                "testCaseId": hashlib.md5(f"k6|{name}|{expr}".encode()).hexdigest(),
                "fullName": f"k6.{scenario}.{name}.{expr}",
                "name": full_name,
                "description": (
                    f"Threshold k6 `{name}: {expr}` pada skenario **{scenario}** "
                    f"({env}). Sumber: `{path.name}`."
                ),
                "status": "passed" if ok else "failed",
                "statusDetails": {} if ok else {"message": f"Threshold tidak terpenuhi: {detail}"},
                "stage": "finished",
                "start": start,
                "stop": stop,
                "labels": labels,
                "parameters": [
                    {"name": "scenario", "value": scenario},
                    {"name": "environment", "value": env},
                    {"name": "hasil", "value": detail},
                    {"name": "data rows", "value": str(meta.get("data_rows"))},
                ],
                "attachments": attachments,
                "steps": [{
                    "name": detail, "status": "passed" if ok else "failed",
                    "stage": "finished", "start": start, "stop": stop,
                }],
            }
            (out / f"{result_json['uuid']}-result.json").write_text(json.dumps(result_json, indent=2), encoding="utf-8")
            count += 1
    return count


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="file summary_*.json atau folder")
    ap.add_argument("--out", required=True, help="folder allure-results")
    ap.add_argument("--env", default="local", help="label environment, mis. 'CI (GitHub Actions)' / 'Internal UAT'")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    files = pick_files(args.inputs)
    if not files:
        print("Tidak ada summary k6 yang ditemukan", file=sys.stderr)
        return 0
    for f in files:
        print(f"{f}: {convert(f, out, args.env)} test case")
    return 0


if __name__ == "__main__":
    sys.exit(main())
