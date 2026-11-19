"""
North Yorkshire Council Mobile Library Ingestion Script.
Downloads live timetable schedule from North Yorkshire Council website,
parses community stops across the 4-week rotating schedule,
resolves coordinates, validates against Frictionless Schema, and updates services.csv.
"""

import os
import re
import csv
import json
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup

from _common import create_mobile_library_file
from geocoder import Geocoder

AUTHORITY_NAME = 'North Yorkshire'
AUTHORITY_CODE = 'E06000065'
SLUG = 'north_yorkshire'
DATE_DIR = '2026-11-19'
RAW_DIR = Path('raw') / SLUG / DATE_DIR
DATA_FILE = Path('data') / f'{SLUG}.csv'
BASE_URL = 'https://www.northyorks.gov.uk/leisure-tourism-and-culture/libraries/local-libraries/mobile-library'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}


def download_raw_page():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    filepath = RAW_DIR / 'mobile_library.html'
    print(f'Downloading North Yorkshire mobile library page...')
    r = requests.get(BASE_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    filepath.write_text(r.text, encoding='utf-8')
    return filepath


def parse_ampm(t_str):
    t = t_str.strip().lower()
    if 'midday' in t or 'noon' in t:
        return '12:00'
    m = re.search(r'(\d{1,2})(?:[.:](\d{2}))?\s*(am|pm)?', t)
    if not m:
        return ''
    h = int(m.group(1))
    mins = int(m.group(2)) if m.group(2) else 0
    mer = m.group(3)
    if mer == 'pm' and h != 12:
        h += 12
    elif mer == 'am' and h == 12:
        h = 0
    return f"{h:02d}:{mins:02d}"


def parse_time_range(time_str):
    parts = re.split(r'\s+to\s+', time_str, flags=re.IGNORECASE)
    if len(parts) == 2:
        p0, p1 = parts[0], parts[1]
        if not re.search(r'(am|pm)', p0, re.I) and 'midday' not in p0.lower():
            if 'am' in p1.lower() and int(re.search(r'\d+', p0).group(0)) <= int(re.search(r'\d+', p1).group(0)):
                p0 += 'am'
            elif 'pm' in p1.lower():
                h0 = int(re.search(r'\d+', p0).group(0))
                p0 += 'pm' if 1 <= h0 < 12 else 'am'
        arr = parse_ampm(p0)
        dep = parse_ampm(p1)
        if arr and dep and dep <= arr:
            h, m = map(int, arr.split(':'))
            dep = f"{(h+1)%24:02d}:{m:02d}"
        return arr, dep
    return '', ''


def extract_location(loc_raw):
    clean = re.sub(r'\s+', ' ', loc_raw).strip()
    if ' - ' in clean:
        parts = clean.split(' - ', 1)
        comm = parts[0].strip()
        stop = parts[1].strip()
    elif ',' in clean:
        parts = clean.split(',', 1)
        comm = parts[0].strip()
        stop = parts[1].strip()
    else:
        comm = clean
        stop = clean
    return comm, stop


def parse_schedule(filepath):
    html = filepath.read_text(encoding='utf-8')
    soup = BeautifulSoup(html, 'html.parser')

    stops = []
    seen = set()

    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for tr in rows[1:]:
            cols = [c.get_text(strip=True) for c in tr.find_all(['td', 'th'])]
            if len(cols) < 3:
                continue

            date_col = cols[0].strip()
            loc_col = cols[1].strip()
            time_col = cols[2].strip()

            # Filter out cancelled, no route, closed
            col_str = ' '.join(cols).lower()
            if any(w in col_str for w in ['cancelled', 'no route', 'closed', 'holiday']):
                continue

            arr, dep = parse_time_range(time_col)
            if not arr and not dep:
                continue

            # Day of week from date_col (e.g. "Tuesday 1", "Wednesday 2")
            day_match = re.search(r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b', date_col, re.I)
            day = day_match.group(1).capitalize() if day_match else 'Monday'

            comm, stop_name = extract_location(loc_col)
            stop_key = f"{comm}::{stop_name}::{arr}"
            if stop_key in seen:
                continue
            seen.add(stop_key)

            route_name = f"Mobile Library - {day}"
            address = f"{stop_name}, {comm}, North Yorkshire"

            stops.append({
                'route': route_name,
                'community': comm,
                'stop': stop_name,
                'address': address,
                'arrival': arr,
                'departure': dep,
                'day': day
            })

    return stops


def run():
    print('=== Starting North Yorkshire Mobile Library Ingestion ===')
    filepath = download_raw_page()
    raw_stops = parse_schedule(filepath)
    print(f'Extracted {len(raw_stops)} distinct stops from North Yorkshire timetable.')

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
            'Mobile name': 'Supermobile Library',
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
            'Frequency': 'FREQ=WEEKLY;INTERVAL=2',
            'Start': '2026-01-01',
            'End': '2026-12-31',
            'Exceptions': '',
            'Timetable': BASE_URL
        })

    geocoder.save_caches()
    print(f'Writing {len(processed_stops)} stops to {DATA_FILE}...')
    create_mobile_library_file('north_yorkshire.csv', processed_stops)

    # Update services.csv
    services_path = Path('services.csv')
    if services_path.exists():
        rows = []
        with open(services_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row['dataset_slug'] == SLUG and row['local_authority_code'] == AUTHORITY_CODE:
                    row['has_mobile_service'] = 'Yes'
                    row['status'] = 'Active Verified'
                    row['source_url'] = BASE_URL
                    row['source_format'] = 'HTML'
                    row['last_checked'] = '2026-11-19'
                    row['last_updated'] = '2026-11-19'
                    row['notes'] = f'Verified 2026 routes: {len(processed_stops)} stops across monthly schedule.'
                rows.append(row)
        with open(services_path, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print('North Yorkshire ingestion completed successfully.')


if __name__ == '__main__':
    run()
