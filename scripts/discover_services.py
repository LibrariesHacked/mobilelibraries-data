"""
Nationwide Discovery and Triage Engine for UK Mobile Library Services.
Scans statutory library authorities, queries official portals, detects active
mobile services vs Home Library Services / closures, and tracks live timetable
landing pages and PDF/download links in services.csv.
"""

import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup

SERVICES_FILE = Path(__file__).resolve().parent.parent / 'services.csv'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}


def load_services():
    with open(SERVICES_FILE, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def save_services(rows):
    fieldnames = list(rows[0].keys())
    with open(SERVICES_FILE, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def update_authority(slug, has_mobile, status, url='', fmt='', notes=''):
    rows = load_services()
    for r in rows:
        if r['dataset_slug'] == slug:
            r['has_mobile_service'] = has_mobile
            r['status'] = status
            r['last_checked'] = '2026-11-18'
            if url:
                r['source_url'] = url
            if fmt:
                r['source_format'] = fmt
            if notes:
                r['notes'] = notes
            break
    save_services(rows)
    print(f"[{slug}] -> Mobile: {has_mobile} | Status: {status} | URL: {url or 'none'}")


if __name__ == '__main__':
    rows = load_services()
    pending = [r for r in rows if r['status'] == 'Pending Discovery']
    print(f"Total statutory authorities: {len(rows)} | Pending discovery: {len(pending)}")
