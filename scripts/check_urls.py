"""Council Timetable URL and Source Availability Checker.

Checks HTTP status, redirects, and accessibility of mobile library source URLs
in services.csv to detect broken links or council website migrations early.

Usage:
  python scripts/check_urls.py [--all] [--timeout 10]
"""

from __future__ import annotations

import argparse
import csv
import ssl
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICES_FILE = ROOT / "services.csv"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

# Custom SSL context allowing verification fallback for councils with outdated intermediate certs
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def check_single_url(url: str, timeout: int = 12) -> tuple[int, str, str]:
    """Test URL accessibility and return (status_code, final_url, error_message)."""
    if not url or not url.startswith("http"):
        return 0, "", "Missing or invalid URL"

    # Always use GET to avoid servers that close or forbid HEAD requests
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
            return resp.status, resp.geturl(), ""
    except urllib.error.HTTPError as e:
        return e.code, url, str(e)
    except urllib.error.URLError as e:
        return 0, url, f"Network error: {e.reason}"
    except Exception as e:
        return 0, url, str(e)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check source URLs in services.csv for broken links.")
    parser.add_argument("--all", action="store_true", help="Check all services (default: active mobile services only)")
    parser.add_argument("--timeout", type=int, default=12, help="HTTP request timeout in seconds (default: 12)")
    parser.add_argument("--threads", type=int, default=8, help="Concurrent worker threads (default: 8)")
    args = parser.parse_args()

    if not SERVICES_FILE.exists():
        print(f"Error: {SERVICES_FILE} not found.")
        return 1

    services_to_check = []
    with open(SERVICES_FILE, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            auth = row.get("local_authority", "")
            has_mobile = row.get("has_mobile_service", "")
            status = row.get("status", "")
            url = (row.get("source_url") or "").strip()

            if not url:
                continue

            if not args.all and has_mobile != "Yes" and "Active" not in status:
                continue

            services_to_check.append({
                "authority": auth,
                "status": status,
                "url": url,
            })

    print(f"Checking {len(services_to_check)} council source URLs (timeout={args.timeout}s)...")

    results = []
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        future_map = {
            executor.submit(check_single_url, s["url"], args.timeout): s
            for s in services_to_check
        }
        for future in as_completed(future_map):
            svc = future_map[future]
            try:
                code, final_url, err = future.result()
                results.append((svc, code, final_url, err))
            except Exception as e:
                results.append((svc, 0, svc["url"], str(e)))

    # Sort results by authority name
    results.sort(key=lambda x: x[0]["authority"])

    ok_count = 0
    redirect_count = 0
    broken_count = 0

    print("\n" + "=" * 60)
    print("Council Timetable URL Status Report")
    print("=" * 60)

    for svc, code, final_url, err in results:
        auth = svc["authority"]
        orig_url = svc["url"]

        if 200 <= code < 300:
            ok_count += 1
            if final_url and final_url != orig_url:
                redirect_count += 1
                print(f"🔄 {auth}: redirected to {final_url}")
            else:
                print(f"✓ {auth}: OK ({code})")
        else:
            broken_count += 1
            print(f"❌ {auth}: HTTP {code} ({err or 'Failed'})")
            print(f"   URL: {orig_url}")

    print("\n" + "-" * 60)
    print(f"Checked: {len(results)} | Accessible: {ok_count} | Redirects: {redirect_count} | Broken: {broken_count}")
    print("-" * 60)

    return 0 if broken_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
