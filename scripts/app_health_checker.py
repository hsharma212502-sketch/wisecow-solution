#!/usr/bin/env python3
"""
Application Health Checker  (PS2 - Objective 4)

Checks whether one or more applications/URLs are UP or DOWN based on their HTTP
response status code and reachability. An app is considered:

    UP    -> a response is received with a status code in the "healthy" set
             (default: any 2xx or 3xx).
    DOWN  -> connection refused / timeout / DNS failure, OR a status code
             outside the healthy set (e.g. 4xx, 5xx).

Results are printed to the console and appended to a log file.

Usage:
    python3 app_health_checker.py https://example.com
    python3 app_health_checker.py https://a.com https://b.com --timeout 5
    python3 app_health_checker.py --file urls.txt --watch 30
    python3 app_health_checker.py https://x.com --ok 200 204

Standard library only (urllib) — no external dependencies.
"""

import argparse
import logging
import os
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime

LOG_FILE = os.environ.get("APP_HEALTH_LOG", "app_health.log")


def setup_logging():
    logger = logging.getLogger("apphealth")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s")
    fh = logging.FileHandler(LOG_FILE)
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def check_url(url, timeout, healthy_codes, insecure=False):
    """
    Probe a single URL.
    Returns a dict: {url, status, code, reason, elapsed_ms}
    status is "UP" or "DOWN".
    """
    ctx = None
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, method="GET",
                                 headers={"User-Agent": "app-health-checker/1.0"})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            elapsed = round((time.monotonic() - start) * 1000)
            code = resp.getcode()
            up = code in healthy_codes if healthy_codes else (200 <= code < 400)
            return {
                "url": url, "status": "UP" if up else "DOWN",
                "code": code, "reason": resp.reason or "", "elapsed_ms": elapsed,
            }
    except urllib.error.HTTPError as e:
        # Server responded, but with an error status code.
        elapsed = round((time.monotonic() - start) * 1000)
        up = e.code in healthy_codes if healthy_codes else False
        return {
            "url": url, "status": "UP" if up else "DOWN",
            "code": e.code, "reason": e.reason, "elapsed_ms": elapsed,
        }
    except urllib.error.URLError as e:
        # Connection refused, DNS failure, TLS error, timeout, etc.
        elapsed = round((time.monotonic() - start) * 1000)
        return {
            "url": url, "status": "DOWN",
            "code": None, "reason": str(e.reason), "elapsed_ms": elapsed,
        }
    except Exception as e:  # noqa: BLE001 - report any unexpected failure as DOWN
        elapsed = round((time.monotonic() - start) * 1000)
        return {
            "url": url, "status": "DOWN",
            "code": None, "reason": repr(e), "elapsed_ms": elapsed,
        }


def report(result, logger):
    code = result["code"] if result["code"] is not None else "-"
    msg = (f"{result['status']:4} | {result['url']} | "
           f"HTTP {code} {result['reason']} | {result['elapsed_ms']}ms")
    if result["status"] == "UP":
        logger.info(msg)
    else:
        logger.warning("ALERT - " + msg)


def load_urls(args):
    urls = list(args.urls)
    if args.file:
        with open(args.file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
    return urls


def main():
    p = argparse.ArgumentParser(description="HTTP application health checker")
    p.add_argument("urls", nargs="*", help="One or more URLs to check")
    p.add_argument("--file", help="File with one URL per line")
    p.add_argument("--timeout", type=float, default=10.0, help="Request timeout (s)")
    p.add_argument("--ok", type=int, nargs="*", default=None,
                   help="Status codes that count as UP (default: any 2xx/3xx)")
    p.add_argument("--insecure", action="store_true",
                   help="Skip TLS verification (useful for self-signed certs)")
    p.add_argument("--watch", type=int, metavar="SECONDS",
                   help="Repeat checks every N seconds (Ctrl-C to stop)")
    args = p.parse_args()

    urls = load_urls(args)
    if not urls:
        p.error("provide at least one URL or --file")

    healthy = set(args.ok) if args.ok else None
    logger = setup_logging()
    logger.info("=== Application Health Checker started at %s ===",
                datetime.now().isoformat(timespec="seconds"))

    def cycle():
        down = 0
        for url in urls:
            res = check_url(url, args.timeout, healthy, args.insecure)
            report(res, logger)
            if res["status"] == "DOWN":
                down += 1
        logger.info("Summary: %d up, %d down (of %d).",
                    len(urls) - down, down, len(urls))
        return down

    try:
        if args.watch:
            while True:
                cycle()
                time.sleep(args.watch)
        else:
            down = cycle()
            raise SystemExit(1 if down else 0)
    except KeyboardInterrupt:
        logger.info("Stopped by user.")


if __name__ == "__main__":
    main()
