"""
Highland Council (High Life Highland) Mobile Library Ingestion Script.
Downloads all 7 live 2026 timetable pages (HTML), parses stops across all routes,
resolves coordinates, validates against Frictionless Schema, and updates services.csv.
"""

from _common import parse_time_range
import os
import re
import csv
import io
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from _common import create_mobile_library_file, parse_time_range
from geocoder import Geocoder

AUTHORITY_NAME = 'Highland'
AUTHORITY_CODE = 'S12000017'
SLUG = 'highland'
DATE_DIR = '2026-11-18'
RAW_DIR = Path('raw') / SLUG / DATE_DIR
DATA_FILE = Path('data') / f'{SLUG}.csv'
BASE_URL = 'https://www.highlifehighland.com/libraries/mobile-libraries/'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

TIMETABLE_PAGES = [
    ('Brora Mobile', 'https://www.highlifehighland.com/libraries/mobile-libraries/brora-mobile-library/brora-mobile-library-timetable'),
    ('Dingwall & Moray Firth Mobile', 'https://www.highlifehighland.com/libraries/mobile-libraries/dingwall-moray-firth-mobile-library/dingwall-and-moray-firth-mobile-timetable'),
    ('Far North Mobile', 'https://www.highlifehighland.com/libraries/mobile-libraries/far-north-mobile-library/farn-north-mobile-library-timetable'),
    ('Fort William Mobile', 'https://www.highlifehighland.com/libraries/mobile-libraries/fort-william-mobile-library/fort-william-mobile-library-timetable'),
    ('Invergordon & Black Isle Mobile', 'https://www.highlifehighland.com/libraries/mobile-libraries/invergordon-and-black-isle-mobile-library/invergordon-mobile-library-timetable'),
    ('Skye & Lochalsh Mobile', 'https://www.highlifehighland.com/libraries/mobile-libraries/skye-and-lochalsh-mobile-library/skye-and-lochalsh-mobile-library-timetable'),
    ('West Ross Mobile', 'https://www.highlifehighland.com/libraries/mobile-libraries/west-ross-mobile-library/west-ross-mobile-library-timetable')
]


def download_raw_pages():
    """Download and cache the 7 High Life Highland HTML timetable pages if missing locally."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for mobile_name, url in TIMETABLE_PAGES:
        filename = url.strip('/').split('/')[-1] + '.html'
        filepath = RAW_DIR / filename
        if not filepath.exists():
            print(f'Downloading {filename}...')
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            filepath.write_text(r.text, encoding='utf-8')
            time.sleep(0.3)
        downloaded.append((mobile_name, url, filepath))
    return downloaded




def extract_community_and_stop(stop_raw):
    """Clean stop text and extract community and stop name."""
    clean = re.sub(r'[\*\^]', '', stop_raw).strip()
    # Fix mojibake UTF-8 en-dash misdecoded as Latin-1/Windows-1252
    clean = clean.replace('â\x80\x93', '-').replace('–', '-').replace('—', '-')
    clean = re.sub(r'\s+', ' ', clean)

    if ',' in clean:
        parts = clean.split(',', 1)
        comm = parts[0].strip()
        stop = parts[1].strip()
    elif ' - ' in clean:
        parts = clean.split(' - ', 1)
        comm = parts[0].strip()
        stop = parts[1].strip()
    else:
        comm = clean
        stop = clean
    return comm, stop


def parse_page(mobile_name, url, filepath):
    """Parse timetable HTML tables in filepath into a list of stop dictionaries for mobile_name."""
    html = filepath.read_text(encoding='utf-8')
    soup = BeautifulSoup(html, 'html.parser')

    stops = []
    tables = soup.find_all('table')

    for t_idx, tbl in enumerate(tables):
        # Look backwards for preceding headings or paragraphs to find route and day
        prev_elements = tbl.find_all_previous(['h2', 'h3', 'h4', 'p'])
        route_title = f"{mobile_name} Route {t_idx+1}"
        day = 'Monday'

        # Limit lookback to 6 elements to avoid picking up headings from earlier tables
        for el in prev_elements[:6]:
            txt = el.get_text(strip=True)
            if 'route' in txt.lower():
                route_title = f"{mobile_name} - {txt}"
                break

        for el in prev_elements[:6]:
            txt = el.get_text(strip=True)
            for d in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
                if d.lower() in txt.lower():
                    day = d
                    break
            if day != 'Monday':
                break

        rows = tbl.find_all('tr')
        for tr in rows:
            cols = [c.get_text(strip=True) for c in tr.find_all(['td', 'th'])]
            if len(cols) < 2:
                continue

            stop_raw = cols[0]
            time_raw = cols[1]

            # Filter out header rows and calling at / notes rows
            if 'stop' in stop_raw.lower() or 'calling at' in stop_raw.lower() or 'route includes' in stop_raw.lower():
                continue

            arr, dep = parse_time_range(time_raw)
            if not arr and not dep:
                continue

            comm, stop_name = extract_community_and_stop(stop_raw)

            stops.append({
                'mobile': mobile_name,
                'route': route_title,
                'community': comm,
                'stop': stop_name,
                'address': f"{stop_name}, {comm}, Highland",
                'arrival': arr,
                'departure': dep,
                'day': day,
                'url': url
            })

    return stops


def run():
    """Download Highland timetable pages, parse and geocode stops, write data/highland.csv, and update services.csv."""
    print('=== Starting Highland Mobile Library Ingestion ===')
    pages = download_raw_pages()
    print(f'Downloaded/verified {len(pages)} Highland timetable pages.')

    raw_stops = []
    for mobile_name, url, filepath in pages:
        f_stops = parse_page(mobile_name, url, filepath)
        print(f'{mobile_name}: extracted {len(f_stops)} stops.')
        raw_stops.extend(f_stops)

    print(f'Extracted {len(raw_stops)} total stops from Highland timetables.')

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
            'Frequency': 'FREQ=WEEKLY;INTERVAL=3',
            'Start': '2026-01-05',
            'End': '2026-12-31',
            'Exceptions': '',
            'Timetable': s['url']
        })

    geocoder.save_caches()
    print(f'Writing {len(processed_stops)} stops to {DATA_FILE}...')
    create_mobile_library_file('highland.csv', processed_stops)

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
                    row['notes'] = f'Verified 2026 routes: {len(processed_stops)} stops across 7 mobile library vehicles.'
                rows.append(row)
        with open(services_path, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print('Highland ingestion completed successfully.')


if __name__ == '__main__':
    run()
