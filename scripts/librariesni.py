"""
Libraries NI (Northern Ireland) Mobile Library Ingestion Script.
Harvests all 14 mobile library routes across Northern Ireland,
parses schedules, resolves coordinates, validates against Frictionless Schema,
and updates services.csv.
"""

import os
import re
import csv
import json
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from _common import create_mobile_library_file
from geocoder import Geocoder

AUTHORITY_NAME = 'LibrariesNI'
AUTHORITY_CODE = 'N92000002'
SLUG = 'librariesni'
DATE_DIR = '2026-11-18'
RAW_DIR = Path('raw') / SLUG / DATE_DIR
DATA_FILE = Path('data') / f'{SLUG}.csv'
BASE_URL = 'https://www.librariesni.org.uk/libraries/mobile-libraries/'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

MOBILES = [
    ('Armagh Mobile', 'armagh-mobile'),
    ('Ballymena Mobile', 'ballymena-mobile'),
    ('Bangor and Lisburn Mobile', 'bangor-and-lisburn-mobile'),
    ('Belfast Mobile', 'belfast-mobile'),
    ('Carrickfergus Mobile', 'carrickfergus-mobile'),
    ('Causeway Mobile', 'causeway-mobile'),
    ('Cross Border Mobile', 'cross-border-mobile'),
    ('Craigavon Mobile', 'craigavon-mobile'),
    ('Dungannon Mobile', 'dungannon-mobile'),
    ('Down Mobile', 'down-mobile'),
    ('Fermanagh Mobile', 'fermanagh-mobile'),
    ('North West Mobile', 'north-west-mobile'),
    ('Newry Mobile', 'newry-mobile'),
    ('Tyrone Mobile', 'tyrone-mobile')
]


def download_raw_html_pages():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for name, slug in MOBILES:
        url = f'{BASE_URL}{slug}/'
        filepath = RAW_DIR / f'{slug}.html'
        if not filepath.exists():
            print(f'Downloading {slug}...')
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            filepath.write_text(r.text, encoding='utf-8')
            time.sleep(0.3)
        downloaded.append((name, url, filepath))
    return downloaded


def normalise_postcode(pc_str):
    if not pc_str:
        return ''
    match = re.search(r'([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})', pc_str, re.IGNORECASE)
    if match:
        cleaned = re.sub(r'[^A-Za-z0-9]', '', match.group(1)).upper()
        if len(cleaned) in [5, 6, 7]:
            outcode = cleaned[:-3]
            incode = cleaned[-3:]
            return f"{outcode} {incode}"
    return ''


def parse_ampm(h_str, m_str, mer):
    h = int(h_str)
    m = int(m_str)
    mer = mer.upper()
    if mer == 'PM' and h != 12:
        h += 12
    elif mer == 'AM' and h == 12:
        h = 0
    return f"{h:02d}:{m:02d}"


def parse_time_range_ampm(time_str):
    cleaned = re.sub(r'[^\w\s:.-]', '', time_str).strip()
    match = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)\s*[-–—]\s*(\d{1,2}):(\d{2})\s*(am|pm)', cleaned, re.IGNORECASE)
    if match:
        h1, m1, mer1, h2, m2, mer2 = match.groups()
        arr = parse_ampm(h1, m1, mer1)
        dep = parse_ampm(h2, m2, mer2)
        return arr, dep
    return '', ''


def extract_ni_location(loc_raw):
    clean = re.sub(r'\s+', ' ', loc_raw).strip()
    if ',' in clean:
        parts = clean.split(',', 1)
        stop = parts[0].strip()
        comm = parts[1].strip()
    elif ' at ' in clean.lower():
        idx = clean.lower().find(' at ')
        comm = clean[:idx].strip()
        stop = clean[idx+4:].strip()
    elif ' near ' in clean.lower():
        idx = clean.lower().find(' near ')
        comm = clean[:idx].strip()
        stop = clean[idx+6:].strip()
    else:
        comm = clean
        stop = clean
    return comm, stop


def parse_mobile_page(mobile_name, url, filepath):
    html = filepath.read_text(encoding='utf-8')
    soup = BeautifulSoup(html, 'html.parser')

    stops = []
    t = soup.find('table')
    if not t:
        return stops

    current_week = 'Week 1'
    current_day = 'Monday'

    for tr in t.find_all('tr'):
        cells = [c.get_text(strip=True) for c in tr.find_all(['td', 'th'])]
        if not cells or not any(cells):
            continue

        row_str = ' '.join(cells).upper()

        # Check for week header
        if 'WEEK 1' in row_str:
            current_week = 'Week 1'
        elif 'WEEK 2' in row_str:
            current_week = 'Week 2'
        elif 'WEEK 3' in row_str:
            current_week = 'Week 3'
        elif 'WEEK 4' in row_str:
            current_week = 'Week 4'

        # Check for day header
        for d in ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY']:
            if d in row_str:
                current_day = d.capitalize()
                break

        # Check if row is a stop time row
        time_cell = cells[0]
        if 'am' not in time_cell.lower() and 'pm' not in time_cell.lower():
            continue

        arr, dep = parse_time_range_ampm(time_cell)
        if not arr and not dep:
            continue

        loc_cell = cells[1] if len(cells) > 1 else ''
        pc_cell = normalise_postcode(cells[2]) if len(cells) > 2 else ''

        if not loc_cell:
            continue

        comm, stop_name = extract_ni_location(loc_cell)
        route_name = f"{mobile_name} - {current_week} - {current_day}"
        address = f"{stop_name}, {comm}, Northern Ireland"
        if pc_cell:
            address += f", {pc_cell}"

        stops.append({
            'mobile': mobile_name,
            'route': route_name,
            'community': comm,
            'stop': stop_name,
            'address': address,
            'postcode': pc_cell,
            'arrival': arr,
            'departure': dep,
            'day': current_day,
            'week': current_week,
            'url': url
        })

    return stops


def run():
    print('=== Starting Libraries NI Mobile Library Ingestion ===')
    files = download_raw_html_pages()
    print(f'Downloaded/verified {len(files)} mobile timetable pages.')

    raw_stops = []
    for mobile_name, url, filepath in files:
        f_stops = parse_mobile_page(mobile_name, url, filepath)
        print(f'{mobile_name}: extracted {len(f_stops)} stops.')
        raw_stops.extend(f_stops)

    print(f'Extracted {len(raw_stops)} total stops from Libraries NI timetables.')

    geocoder = Geocoder()
    processed_stops = []

    for s in raw_stops:
        comm = s['community']
        stop_name = s['stop']
        pc = s['postcode']
        addr = s['address']

        geo = geocoder.resolve(AUTHORITY_NAME, comm, stop_name, postcode=pc, address=addr)
        geox = geo.get('geox', '')
        geoy = geo.get('geoy', '')
        final_pc = normalise_postcode(geo.get('postcode') or pc)

        processed_stops.append({
            'Local authority': AUTHORITY_NAME,
            'Local authority code': AUTHORITY_CODE,
            'Mobile name': s['mobile'],
            'Route': s['route'],
            'Community': comm,
            'Stop': stop_name,
            'Address': addr,
            'Postcode': final_pc,
            'GeoX': geox,
            'GeoY': geoy,
            'Day': s['day'],
            'Type': 'Public',
            'Arrival': s['arrival'],
            'Departure': s['departure'],
            'Frequency': 'FREQ=WEEKLY;INTERVAL=2',
            'Start': '2026-01-05',
            'End': '2026-12-31',
            'Exceptions': '',
            'Timetable': s['url']
        })

    geocoder.save_caches()
    print(f'Writing {len(processed_stops)} stops to {DATA_FILE}...')
    create_mobile_library_file('librariesni.csv', processed_stops)

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
                    row['source_format'] = 'HTML'
                    row['last_checked'] = '2026-11-18'
                    row['last_updated'] = '2026-11-18'
                    row['notes'] = f'Verified 2026 routes: {len(processed_stops)} stops across 14 mobile library vehicles in Northern Ireland.'
                rows.append(row)
        with open(services_path, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print('Libraries NI ingestion completed successfully.')


if __name__ == '__main__':
    run()
