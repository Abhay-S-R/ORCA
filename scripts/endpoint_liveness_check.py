#!/usr/bin/env python
"""Endpoint liveness sweep (plan §1.2). Run before Phase 1 agents are coded
against these — every one has a cached local fallback, so a dead endpoint is
a degradation to note, not a stoppage.

Usage: python scripts/endpoint_liveness_check.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
INCOIS_CERT = REPO_ROOT / "certs" / "incois_cert.pem"

ENDPOINTS = [
    ("INCOIS ERDDAP", "https://erddap.incois.gov.in/erddap/index.html", str(INCOIS_CERT)),
    (
        "INCOIS PFZ text (SEC001)",
        "https://incois.gov.in/MarineFisheries/TextData?secid=SEC001",
        True,
    ),
    (
        "Open-Meteo Marine",
        "https://marine-api.open-meteo.com/v1/marine?latitude=8.80&longitude=78.14&hourly=wave_height",
        True,
    ),
    ("IMD API", "https://api.imd.gov.in", True),
    ("NDMA SACHET CAP", "https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails", True),
]


def check(name: str, url: str, verify: str | bool) -> tuple[str, int | str]:
    try:
        resp = requests.get(url, timeout=8, verify=verify)
        return name, resp.status_code
    except requests.exceptions.SSLError as e:
        return name, f"SSL error — {e}"
    except requests.exceptions.RequestException as e:
        return name, f"unreachable — {e}"


def main() -> int:
    print(f"{'endpoint':<28} result")
    print("-" * 60)
    dead = 0
    for name, url, verify in ENDPOINTS:
        _, result = check(name, url, verify)
        ok = isinstance(result, int) and result < 500
        if not ok:
            dead += 1
        print(f"{name:<28} {result}")
    print("-" * 60)
    print(
        f"{dead}/{len(ENDPOINTS)} degraded. Every source has a cached fallback in data/ "
        "(plan §1.2) — this is informational, not blocking."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
