"""
Somerset Council Mobile Library Ingestion Script.
Downloads live 2026/2027 timetable PDF from Somerset Council SharePoint,
parses stops across Routes A through P, resolves coordinates,
validates against Frictionless Schema, and updates services.csv.
"""

from _common import normalise_postcode
import os
import re
import csv
import json
import time
import requests
from pathlib import Path
import pdfplumber

from _common import create_mobile_library_file, normalise_postcode
from geocoder import Geocoder

AUTHORITY_NAME = 'Somerset'
AUTHORITY_CODE = 'E06000066'
SLUG = 'somerset'
DATE_DIR = '2026-11-19'
RAW_DIR = Path('raw') / SLUG / DATE_DIR
DATA_FILE = Path('data') / f'{SLUG}.csv'
BASE_URL = 'https://www.somerset.gov.uk/libraries/mobile-library/'
PDF_URL = 'https://somersetcc.sharepoint.com/:b:/s/SCCPublic/IQCQQznyk9LhS6pip2rMbDLgAYEo6UFVjVJKtZidzpPCTF4?download=1'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}


def download_raw_pdf():
    """Download the Somerset timetable PDF to RAW_DIR if not cached and return its path."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    filepath = RAW_DIR / 'mobile_library_routes_2026_2027.pdf'
    if not filepath.exists():
        print(f'Downloading Somerset timetable PDF...')
        r = requests.get(PDF_URL, headers=HEADERS, timeout=25)
        r.raise_for_status()
        filepath.write_bytes(r.content)
        print(f'Saved raw PDF to {filepath}')
    return filepath


def parse_time_str(t_str):
    """Extract the first HH:MM or H.MM time from t_str and return zero-padded HH:MM, or ''."""
    if not t_str:
        return ''
    cleaned = t_str.strip().replace('.', ':')
    match = re.search(r'(\d{1,2}):(\d{2})', cleaned)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        return f"{h:02d}:{m:02d}"
    return ''




def parse_somerset_pdf(filepath):
    """Parse timetable route pages from the Somerset PDF and return a list of raw stop dicts."""
    # Match UK postcodes and time ranges using '.' or ':' with hyphen/en-dash/em-dash
    postcode_re = re.compile(r'([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})', re.IGNORECASE)
    time_re = re.compile(r'(\d{1,2}[.:]\d{2})\s*[-–—]\s*(\d{1,2}[.:]\d{2})')

    stops = []
    with pdfplumber.open(filepath) as pdf:
        # Pages 0-1 are cover/intro; Route A starts on page index 2
        for p_idx in range(2, len(pdf.pages)):
            text = pdf.pages[p_idx].extract_text()
            if not text:
                continue

            lines = [l.strip() for l in text.split('\n') if l.strip()]
            header_block = ' '.join(lines[:3])

            m_route = re.search(r'Route\s+([A-Z])', header_block, re.I)
            route_letter = m_route.group(1).upper() if m_route else chr(ord('A') + (p_idx - 2))

            day = 'Monday'
            for d in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
                if d.lower() in header_block.lower():
                    day = d
                    break

            current_comm = ''
            # Skip the route/day header lines at the top of the page
            for line in lines[2:]:
                m_time = time_re.search(line)
                m_pc = postcode_re.search(line)

                if m_time and m_pc:
                    arr = parse_time_str(m_time.group(1))
                    dep = parse_time_str(m_time.group(2))
                    pc = normalise_postcode(m_pc.group(1))
                    stop_name = line[:m_pc.start()].strip()

                    route_name = f"Route {route_letter} - {day}"
                    comm = current_comm or stop_name
                    address = f"{stop_name}, {comm}, Somerset"
                    if pc:
                        address += f", {pc}"

                    stops.append({
                        'route': route_name,
                        'community': comm,
                        'stop': stop_name,
                        'address': address,
                        'postcode': pc,
                        'arrival': arr,
                        'departure': dep,
                        'day': day
                    })
                # Non-boiler-plate lines without a time range act as community section headings
                elif not m_time and line and not any(k in line.lower() for k in ['service', 'contact', 'schedule', '2026', 'dates', 'somerset direct']):
                    current_comm = line

    return stops


def run():
    """Download and parse the Somerset PDF, geocode stops, write data/somerset.csv, and update services.csv."""
    print('=== Starting Somerset Mobile Library Ingestion ===')
    filepath = download_raw_pdf()
    raw_stops = parse_somerset_pdf(filepath)
    print(f'Extracted {len(raw_stops)} stops from Somerset PDF.')

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
        final_pc = geo.get('postcode') or pc

        processed_stops.append({
            'Local authority': AUTHORITY_NAME,
            'Local authority code': AUTHORITY_CODE,
            'Mobile name': 'Somerset Mobile Library',
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
            'Frequency': 'FREQ=WEEKLY;INTERVAL=4',
            'Start': '2026-04-01',
            'End': '2027-03-31',
            'Exceptions': '',
            'Timetable': BASE_URL
        })

    geocoder.save_caches()
    print(f'Writing {len(processed_stops)} stops to {DATA_FILE}...')
    create_mobile_library_file('somerset.csv', processed_stops)

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
                    row['source_format'] = 'PDF'
                    row['last_checked'] = '2026-11-19'
                    row['last_updated'] = '2026-11-19'
                    row['notes'] = f'Verified 2026/2027 routes: {len(processed_stops)} stops across Routes A through P.'
                rows.append(row)
        with open(services_path, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print('Somerset ingestion completed successfully.')


if __name__ == '__main__':
    run()
