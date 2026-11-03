"""Konfigurasi functional test BDD untuk POST /v1/report_mauto.

Environment variable:
  REPORT_MAUTO_BASE_URL  default http://localhost:8013
  REPORT_MAUTO_API_KEY   default: VALID_API_KEYS dari .env di root project
  API_KEY_NAME           default: dari .env, fallback X-API-KEY
"""
import os
from pathlib import Path

import allure
import httpx
import pytest
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
_ENV = dotenv_values(ROOT / ".env")

BASE_URL = os.getenv("REPORT_MAUTO_BASE_URL", "http://localhost:8013").rstrip("/")
API_KEY = os.getenv("REPORT_MAUTO_API_KEY") or _ENV.get("VALID_API_KEYS") or ""
API_KEY_NAME = os.getenv("API_KEY_NAME") or _ENV.get("API_KEY_NAME") or "X-API-KEY"

_SEVERITIES = {s.value for s in allure.severity_level}


@pytest.fixture(scope="session")
def client():
    # trust_env=False: abaikan http_proxy/https_proxy agar request ke localhost
    # tidak dibelokkan ke proxy korporat (yang membalas 403).
    with httpx.Client(base_url=BASE_URL, timeout=30, trust_env=False) as c:
        yield c


class ScenarioContext(dict):
    """dict biasa, tetapi repr-nya disamarkan.

    pytest menampilkan argumen fungsi saat assertion gagal; tanpa ini API key
    (di headers) dan data nasabah ikut tercetak ke console dan report Allure.
    """

    def __repr__(self):
        return f"<ScenarioContext keys={sorted(self)}>"


@pytest.fixture
def ctx():
    """State per scenario yang dibagi antar step."""
    return ScenarioContext(headers={"Content-Type": "application/json"})


class Secret:
    """Pembungkus API key yang repr-nya disamarkan.

    Allure mencatat argumen step sebagai parameter report; sengaja bukan subclass
    str karena Allure merepresentasikan str apa adanya. Pakai .value saat dikirim.
    """

    def __init__(self, value: str):
        self.value = value

    def __repr__(self):
        return "'***'"


@pytest.fixture(scope="session")
def api_key():
    if not API_KEY:
        pytest.exit("API key tidak ditemukan: set REPORT_MAUTO_API_KEY atau VALID_API_KEYS di .env", 2)
    return Secret(API_KEY)


@pytest.fixture(scope="session")
def api_key_name():
    return API_KEY_NAME


@pytest.hookimpl(trylast=True)
def pytest_bdd_before_scenario(request, feature, scenario):
    """Petakan struktur Gherkin ke label Allure.

    Feature -> feature, Rule (TS-xx) -> story, Scenario (TC-xx) -> title,
    tag @severity:x -> severity, tag @epic:x -> epic, tag @TC-xx -> id.
    """
    if scenario.rule is not None:
        allure.dynamic.story(scenario.rule.name)
    tags = set(scenario.tags) | set(feature.tags)
    for tag in tags:
        key, _, value = tag.partition(":")
        if key == "severity" and value in _SEVERITIES:
            allure.dynamic.severity(allure.severity_level(value))
        elif key == "epic" and value:
            allure.dynamic.epic(value.replace("_", " "))
        elif tag.startswith("TC-"):
            allure.dynamic.id(tag)
