"""
Cornwall Council Mobile Library Ingestion Script.
Downloads all live 2026/2027 timetables (DOCX), parses stops for East and West mobile libraries,
resolves coordinates, validates against Frictionless Schema, and updates services.csv.
"""

import os
import re
import csv
import io
import time
import zipfile
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from _common import create_mobile_library_file
from geocoder import Geocoder

AUTHORITY_NAME = 'Cornwall'
AUTHORITY_CODE = 'E06000052'
SLUG = 'cornwall'
DATE_DIR = '2026-11-18'
RAW_DIR = Path('raw') / SLUG / DATE_DIR
DATA_FILE = Path('data') / f'{SLUG}.csv'
BASE_URL = 'https://www.cornwall.gov.uk/libraries-museums-and-archives/libraries/mobile-library/'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

TIMETABLE_URLS = [
    ('West Mobile - Week 1', 'https://www.cornwall.gov.uk/media/swfbtnis/wk1-july26-jan-27.docx'),
    ('West Mobile - Week 2', 'https://www.cornwall.gov.uk/media/rgplt23w/wk2-july26-jan27.docx'),
    ('East Mobile - Week 3', 'https://www.cornwall.gov.uk/media/1mbhfygc/east_week_3_schedule-nov2026-march-27-003.docx'),
    ('East Mobile - Week 4', 'https://www.cornwall.gov.uk/media/io5omgwj/east-week-4-schedule_nov-26-march-27.docx'),
    ('West Mobile - The Roseland', 'https://www.cornwall.gov.uk/media/tf5kxzgc/roseland-july26-feb27.docx'),
    ('East Mobile - Padstow', 'https://www.cornwall.gov.uk/media/4xmkccwu/padstow-nov-26-mar-27.docx')
]


def download_raw_files():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for label, url in TIMETABLE_URLS:
        filename = url.split('/')[-1]
        filepath = RAW_DIR / filename
        if not filepath.exists():
            print(f'Downloading {filename}...')
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            filepath.write_bytes(r.content)
            time.sleep(0.3)
        downloaded.append((label, url, filepath))
    return downloaded


def parse_cornwall_time_range(raw):
    """Parse time range like '0930 - 0950', '10:00 – 10.35', '13.55-14:35'."""
    times = re.findall(r'(\d{1,2})[:.]?(\d{2})', raw)
    if len(times) >= 2:
        h1, m1 = int(times[0][0]), int(times[0][1])
        h2, m2 = int(times[1][0]), int(times[1][1])
        if h2 < h1 and h2 < 12:
            h2 += 12
        arr = f"{h1:02d}:{m1:02d}"
        dep = f"{h2:02d}:{m2:02d}"
        return arr, dep
    return '', ''


def parse_file(label, url, filepath):
    stops = []
    with zipfile.ZipFile(filepath) as z:
        xml = z.read('word/document.xml').decode('utf-8')
    soup = BeautifulSoup(xml, 'xml')

    mobile_name = 'West Cornwall Mobile' if 'West' in label else 'East Cornwall Mobile'

    seen_stops_on_route = set()

    for tbl in soup.find_all('w:tbl'):
        rows = []
        for tr in tbl.find_all('w:tr'):
            cells = []
            for tc in tr.find_all('w:tc'):
                cell_text = ''.join(t.text for t in tc.find_all('w:t')).strip()
                cells.append(cell_text)
            if any(cells):
                rows.append(cells)

        if not rows:
            continue

        # Header detection
        header_text = ' '.join(rows[0]).lower()
        day = 'Monday'
        for d in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
            if d.lower() in header_text:
                day = d
                break

        # Check if table contains stop data (has time pattern in col 1)
        # First row is usually header like "TUESDAY – WEEK 1"
        for r in rows[1:]:
            if len(r) < 2:
                continue
            loc_str = r[0].strip()
            time_str = r[1].strip()

            arr, dep = parse_cornwall_time_range(time_str)
            if not arr and not dep:
                continue

            # Split location into Community and Stop
            # e.g. "Gweek – The Quay", "St Germans- Alms Houses", "Rose"
            loc_clean = re.sub(r'\s+', ' ', loc_str).strip()
            # If dash present
            if any(dash in loc_clean for dash in ['–', '-', '—']):
                parts = re.split(r'\s*[–—\-]\s*', loc_clean, maxsplit=1)
                comm = parts[0].strip()
                stop = parts[1].strip() if len(parts) > 1 else comm
            else:
                comm = loc_clean
                stop = loc_clean

            # Normalize stop if empty
            if not stop:
                stop = comm

            route_name = f"{label} - {day}"
            stop_key = f"{route_name}::{comm}::{stop}::{arr}"
            if stop_key in seen_stops_on_route:
                continue
            seen_stops_on_route.add(stop_key)

            stops.append({
                'label': label,
                'mobile': mobile_name,
                'route': route_name,
                'community': comm,
                'stop': stop,
                'address': f"{stop}, {comm}, Cornwall",
                'arrival': arr,
                'departure': dep,
                'day': day,
                'url': url
            })

    return stops


def run():
    print('=== Starting Cornwall Mobile Library Ingestion ===')
    files = download_raw_files()
    print(f'Downloaded/verified {len(files)} Cornwall timetable files.')

    raw_stops = []
    for label, url, filepath in files:
        f_stops = parse_file(label, url, filepath)
        print(f'{label}: extracted {len(f_stops)} stops.')
        raw_stops.extend(f_stops)

    print(f'Extracted {len(raw_stops)} total stops from Cornwall timetables.')

    geocoder = Geocoder()
    processed_stops = []

    for s in raw_stops:
        comm = s['community']
        stop_name = s['stop']
        addr = s['address']

        geo = geocoder.resolve(AUTHORITY_NAME, comm, stop_name, address=addr)
        geox = geo.get('geox', '')
        geoy = geo.get('geoy', '')
        pc = geo.get('postcode', '')

        processed_stops.append({
            'Local authority': AUTHORITY_NAME,
            'Local authority code': AUTHORITY_CODE,
            'Mobile name': s['mobile'],
            'Route': s['route'],
            'Community': comm,
            'Stop': stop_name,
            'Address': addr,
            'Postcode': pc,
            'GeoX': geox,
            'GeoY': geoy,
            'Day': s['day'],
            'Type': 'Public',
            'Arrival': s['arrival'],
            'Departure': s['departure'],
            'Frequency': 'FREQ=WEEKLY;INTERVAL=4',
            'Start': '2026-07-01',
            'End': '2027-03-31',
            'Exceptions': '',
            'Timetable': s['url']
        })

    geocoder.save_caches()
    print(f'Writing {len(processed_stops)} stops to {DATA_FILE}...')
    create_mobile_library_file('cornwall.csv', processed_stops)

    # Update services.csv
    services_path = Path('services.csv')
    if services_path.exists():
        rows = []
        with open(services_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row['dataset_slug'] == SLUG:
                    row['has_mobile_service'] = 'Yes'
                    row['status'] = 'Active Verified'
                    row['source_url'] = BASE_URL
                    row['source_format'] = 'DOCX'
                    row['last_checked'] = '2026-11-18'
                    row['last_updated'] = '2026-11-18'
                    row['notes'] = f'Verified 2026/2027 routes: {len(processed_stops)} stops across East and West mobiles.'
                rows.append(row)
        with open(services_path, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print('Cornwall ingestion completed successfully.')


if __name__ == '__main__':
    run()
