"""
Unified AI-Assisted Extractor for Mobile Library Timetables.
Extracts structured stop records from raw HTML or PDF documents
and normalises them into the LibrariesHacked Table Schema format.

Integrates directly with:
- Geocoder (with persistent stops reference cache)
- Frictionless schema validator
- Services registry tracker
"""

import argparse
import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path
import pdfplumber

from _common import create_mobile_library_file, SCHEMA_COLUMNS
from geocoder import Geocoder

RAW_DIR = Path(__file__).resolve().parent.parent / 'raw'
DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
SERVICES_FILE = Path(__file__).resolve().parent.parent / 'services.csv'

MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
}

DATE_PATTERN = re.compile(
    r'(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)',
    re.IGNORECASE
)

TIME_PATTERN = re.compile(r'(\d{1,2}[:.]\d{2})\s*[-–to\s]+\s*(\d{1,2}[:.]\d{2})')


def normalise_time(t_str):
    t = str(t_str).strip().replace(' ', '')
    if '.' in t:
        parts = t.split('.')
    elif ':' in t:
        parts = t.split(':')
    else:
        return t
    try:
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    except ValueError:
        return t


def normalise_day(text):
    for d in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
        if d.lower() in text.lower():
            return d
    return ''


class AITimetableExtractor:
    def __init__(self, authority_slug):
        self.slug = authority_slug
        self.geocoder = Geocoder()
        self.authority_meta = self._load_authority_meta()

    def _load_authority_meta(self):
        if not SERVICES_FILE.exists():
            return {}
        with open(SERVICES_FILE, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get('dataset_slug') == self.slug:
                    return row
        return {}

    def extract_from_pdf(self, pdf_path, mobile_name='Mobile', frequency='FREQ=WEEKLY;INTERVAL=2', default_start='2026-01-05'):
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        extracted_stops = []
        la_name = self.authority_meta.get('local_authority', self.slug.replace('_', ' ').title())
        la_code = self.authority_meta.get('local_authority_code', '')
        source_url = self.authority_meta.get('source_url', '')

        with pdfplumber.open(pdf_file) as pdf:
            for p_idx, page in enumerate(pdf.pages):
                text = page.extract_text() or ''
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                header = lines[0] if lines else f"Route {p_idx+1}"

                # Infer Route & Day from header
                route_match = re.search(r'Route\s+(\d+|[A-Z]+)', header, re.IGNORECASE)
                route_str = f"Route {route_match.group(1)}" if route_match else f"Route {p_idx+1}"
                day_str = normalise_day(header) or 'Monday'

                # Extract start date
                date_matches = DATE_PATTERN.findall(text)
                start_date = default_start
                if date_matches:
                    d, m = date_matches[0]
                    month_num = MONTHS.get(m.lower(), 1)
                    start_date = f"2026-{month_num:02d}:{int(d):02d}"

                # Extract tables
                tables = page.extract_tables()
                found_table = False
                for t in tables:
                    if not t or len(t) < 2:
                        continue
                    first_row = [str(c).lower() if c else '' for c in t[0]]
                    if any(k in c for c in first_row for k in ['village', 'stop', 'location', 'community']):
                        found_table = True
                        for row in t[1:]:
                            if not row or len(row) < 3:
                                continue
                            comm = (row[0] or '').strip().replace('\n', ' ')
                            stop_loc = (row[1] or '').strip().replace('\n', ' ')
                            arr = (row[2] or '').strip()
                            dep = (row[3] or '').strip() if len(row) > 3 else ''

                            if not dep and arr:
                                # Check if arrival contains a range like '10.00 - 10.30'
                                tm = TIME_PATTERN.search(arr)
                                if tm:
                                    arr, dep = tm.groups()

                            if not arr or not stop_loc:
                                continue

                            arr_fmt = normalise_time(arr)
                            dep_fmt = normalise_time(dep) if dep else arr_fmt

                            # Geocode stop via reference cache & fallback resolvers
                            geo = self.geocoder.resolve(la_name, comm, stop_loc)
                            geox = geo.get('geox', '')
                            geoy = geo.get('geoy', '')
                            postcode = geo.get('postcode', '')

                            address = f"{stop_loc}, {comm}, {la_name}".strip(', ')

                            extracted_stops.append({
                                'Local authority': la_name,
                                'Local authority code': la_code,
                                'Mobile name': mobile_name,
                                'Route': route_str,
                                'Community': comm,
                                'Stop': stop_loc,
                                'Address': address,
                                'Postcode': postcode,
                                'GeoX': geox,
                                'GeoY': geoy,
                                'Day': day_str,
                                'Type': 'Public',
                                'Arrival': arr_fmt,
                                'Departure': dep_fmt,
                                'Frequency': frequency,
                                'Start': start_date,
                                'End': '',
                                'Exceptions': '',
                                'Timetable': source_url
                            })

        # Save any new geocodes learned during parsing
        self.geocoder.save_caches()

        out_csv = f"{self.slug}.csv"
        create_mobile_library_file(out_csv, extracted_stops)
        print(f"[{self.slug}] Successfully extracted {len(extracted_stops)} stops to data/{out_csv}")
        return extracted_stops


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='AI Timetable Extractor')
    parser.add_argument('--authority', '-a', required=True, help='Authority dataset slug')
    parser.add_argument('--pdf', '-p', required=True, help='Path to timetable PDF')
    parser.add_argument('--mobile', '-m', default='Mobile', help='Mobile library vehicle name')
    parser.add_argument('--frequency', '-f', default='FREQ=WEEKLY;INTERVAL=2', help='iCal recurrence rule')
    args = parser.parse_args()

    extractor = AITimetableExtractor(args.authority)
    extractor.extract_from_pdf(args.pdf, mobile_name=args.mobile, frequency=args.frequency)
