#!/usr/bin/env python3
"""Buat GitHub Issue dari file docs/issues/*.md (front matter: title, labels).

    GITHUB_TOKEN=<token dengan scope repo/issues> python3 docs/issues/create_issues.py [--repo owner/name] [--dry-run]

Issue dengan judul yang sama (open) tidak dibuat ulang.

Di jaringan dengan proxy TLS korporat, arahkan Python ke CA sistem:
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt GITHUB_TOKEN=... python3 docs/issues/create_issues.py

Sudah dibuat 2026-11-03: #2 (§9.1), #3 (§9.2), #4 (§9.3), #5 (§9.4).
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.github.com"


def parse(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    meta, body = m.group(1), m.group(2).strip()
    title = re.search(r'^title:\s*"(.*)"\s*$', meta, re.M).group(1)
    labels = [x.strip() for x in re.search(r"^labels:\s*\[(.*)\]", meta, re.M).group(1).split(",") if x.strip()]
    return title, labels, body


def call(method, url, token, data=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(data).encode() if data else None, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "User-Agent": "report-mauto-issue-script"})
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="sivi-shahab/integrasi-mauto-cdbso")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token and not args.dry_run:
        sys.exit("Set GITHUB_TOKEN terlebih dahulu")

    files = sorted(Path(__file__).parent.glob("9.*.md"))
    existing = set()
    if not args.dry_run:
        q = urllib.parse.urlencode({"state": "open", "per_page": 100})
        existing = {i["title"] for i in call("GET", f"{API}/repos/{args.repo}/issues?{q}", token)}
    for f in files:
        title, labels, body = parse(f)
        if title in existing:
            print(f"skip (sudah ada): {title}")
            continue
        if args.dry_run:
            print(f"[dry-run] {title} labels={labels}")
            continue
        issue = call("POST", f"{API}/repos/{args.repo}/issues", token,
                     {"title": title, "body": body, "labels": labels})
        print(f"#{issue['number']} {issue['html_url']}")


if __name__ == "__main__":
    main()
