"""
Angus Council (ANGUSalive) Mobile Library Ingestion Script.
Downloads live 2026/2027 timetable PDF for Van 1 (Isla) and Van 2 (Glen),
parses stop tables, resolves coordinates via Geocoder,
validates against Frictionless Schema, and updates services.csv.
"""

import os
import re
import csv
import io
import time
import requests
from pathlib import Path
import pdfplumber

from _common import create_mobile_library_file
from geocoder import Geocoder

AUTHORITY_NAME = 'Angus'
AUTHORITY_CODE = 'S12000041'
SLUG = 'angus'
DATE_DIR = '2026-11-18'
RAW_DIR = Path('raw') / SLUG / DATE_DIR
DATA_FILE = Path('data') / f'{SLUG}.csv'
BASE_URL = 'https://angusalive.scot/libraries/mobile-library/'
PDF_URL = 'https://angusalive.scot/wp-content/uploads/2026/10/Mobile-Library-Timetable-Aut-2026-Spring-2027-.pdf'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}


def download_raw_pdf():
    """Download the Angus timetable PDF to RAW_DIR if missing and return its local Path."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    filepath = RAW_DIR / 'Mobile-Library-Timetable-Aut-2026-Spring-2027-.pdf'
    if not filepath.exists():
        print('Downloading Angus timetable PDF...')
        r = requests.get(PDF_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        filepath.write_bytes(r.content)
    return filepath


def extract_angus_location(loc_raw):
    """Split a raw Angus location string into (community, stop) via parentheses or '/'."""
    # e.g. "Wellbank (Gagiebank)", "Inverarity (by school)*", "Edzell (Memorial Hall)", "Lunanhead (Midrow)"
    # Strip footnote symbols (*, ^, ellipsis) and trailing punctuation
    clean = re.sub(r'[\*\^…]+', '', loc_raw).strip()
    clean = re.sub(r'[\.\s]+$', '', clean)

    if '(' in clean and ')' in clean:
        parts = clean.split('(', 1)
        comm = parts[0].strip()
        stop = parts[1].replace(')', '').strip()
    elif '/' in clean:
        parts = clean.split('/', 1)
        comm = parts[0].strip()
        stop = parts[1].strip()
    else:
        comm = clean
        stop = clean
    return comm, stop


def parse_angus_pdf(filepath):
    """Extract raw stop dicts from the two-page Angus PDF tables by van, week, and day."""
    stops = []
    with pdfplumber.open(filepath) as pdf:
        for p_idx, page in enumerate(pdf.pages):
            # Page 0 holds Van 1 (Isla); page 1 holds Van 2 (Glen)
            van_name = 'Van 1 - Isla' if p_idx == 0 else 'Van 2 - Glen'
            tables = page.extract_tables()

            # 8 tables per page: Mon-Thu pairs where even indices are Week 1 and odd are Week 2
            for t_idx, table in enumerate(tables):
                week = 'Week 1' if t_idx % 2 == 0 else 'Week 2'
                day = 'Monday'
                if t_idx in [2, 3]:
                    day = 'Tuesday'
                elif t_idx in [4, 5]:
                    day = 'Wednesday'
                elif t_idx in [6, 7]:
                    day = 'Thursday'

                for row in table:
                    if len(row) < 2 or not row[1]:
                        continue
                    time_raw = row[1].strip()
                    # Match arrival-departure time range separated by hyphen or en-dash
                    m = re.search(r'(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})', time_raw)
                    if not m:
                        continue

                    arr, dep = m.group(1), m.group(2)
                    loc_raw = row[0].strip()
                    comm, stop_name = extract_angus_location(loc_raw)

                    route_name = f"{van_name} - {week} - {day}"
                    address = f"{stop_name}, {comm}, Angus"

                    stops.append({
                        'mobile': van_name,
                        'route': route_name,
                        'community': comm,
                        'stop': stop_name,
                        'address': address,
                        'arrival': arr,
                        'departure': dep,
                        'day': day,
                        'week': week
                    })

    return stops


def run():
    """Fetch and parse the Angus timetable PDF, geocode stops, write data/angus.csv, and update services.csv."""
    print('=== Starting Angus Mobile Library Ingestion ===')
    pdf_path = download_raw_pdf()
    raw_stops = parse_angus_pdf(pdf_path)
    print(f'Extracted {len(raw_stops)} stops from Angus PDF.')

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
            'Frequency': 'FREQ=WEEKLY;INTERVAL=2',
            'Start': '2026-10-05',
            'End': '2027-04-01',
            'Exceptions': '',
            'Timetable': PDF_URL
        })

    geocoder.save_caches()
    print(f'Writing {len(processed_stops)} stops to {DATA_FILE}...')
    create_mobile_library_file('angus.csv', processed_stops)

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
                    row['source_url'] = PDF_URL
                    row['source_format'] = 'PDF'
                    row['last_checked'] = '2026-11-18'
                    row['last_updated'] = '2026-11-18'
                    row['notes'] = f'Verified 2026/2027 routes: {len(processed_stops)} stops across Van 1 (Isla) and Van 2 (Glen).'
                rows.append(row)
        with open(services_path, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print('Angus ingestion completed successfully.')


if __name__ == '__main__':
    run()
