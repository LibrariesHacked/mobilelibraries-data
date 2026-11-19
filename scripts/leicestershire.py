"""
Processes raw Leicestershire mobile library PDF timetables from leicestershire.gov.uk
and produces a standardised CSV (data/leicestershire.csv) adhering to mobile-library-stops.json schema.
"""

import json
import re
from pathlib import Path
import pdfplumber

from _common import create_mobile_library_file

RAW_DIR = Path(__file__).resolve().parent.parent / 'raw' / 'leicestershire'
DATA_DATE = '2026-11-18'
TIMETABLE_PDF_DIR = RAW_DIR / DATA_DATE
GEOCODE_CACHE = RAW_DIR / 'geocode_cache.json'

LOCAL_AUTHORITY = 'Leicestershire'
LOCAL_AUTHORITY_CODE = 'E10000018'
SOURCE_URL = 'https://www.leicestershire.gov.uk/leisure-and-community/libraries/mobile-library-routes'

FILES = [
    ('Mobile A', TIMETABLE_PDF_DIR / 'Mobile-Library-A-Timetable-Melton.pdf',
     'https://www.leicestershire.gov.uk/sites/default/files/2025-02/Mobile-Library-A-Timetable-Melton.pdf'),
    ('Mobile B', TIMETABLE_PDF_DIR / 'Mobile-library-B-timetable-Lutterworth.pdf',
     'https://www.leicestershire.gov.uk/sites/default/files/2025-10/Mobile-library-B-timetable-Lutterworth.pdf'),
    ('Mobile C', TIMETABLE_PDF_DIR / 'Mobile-library-C-timetable-Coalville.pdf',
     'https://www.leicestershire.gov.uk/sites/default/files/2025-02/Mobile-library-C-timetable-Coalville.pdf')
]

months = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
}

# Matches day-and-month dates such as "12th January" to infer each route's baseline start date
date_pattern = re.compile(
    r'(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)',
    re.IGNORECASE
)


def normalise_time(t_str):
    """Normalise a dot- or colon-separated time string (e.g. '9.30', '14:05') to zero-padded HH:MM."""
    t_str = t_str.strip().replace(' ', '')
    if '.' in t_str:
        h, m = t_str.split('.')
    elif ':' in t_str:
        h, m = t_str.split(':')
    else:
        return t_str
    return f"{int(h):02d}:{int(m):02d}"


def run():
    """Parse stop tables and rota dates from Leicestershire timetable PDFs, apply cached geocodes, and write data/leicestershire.csv."""
    geocode_dict = {}
    if GEOCODE_CACHE.exists():
        geocode_dict = json.loads(GEOCODE_CACHE.read_text(encoding='utf-8'))

    stops_list = []

    for mobile_name, pdf_path, timetable_url in FILES:
        if not pdf_path.exists():
            print(f"File not found: {pdf_path}")
            continue

        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                text = page.extract_text()
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                if not lines:
                    continue

                header = lines[0]
                # Split on ASCII hyphen or en-dash to separate route name and weekday in page header
                parts = [p.strip() for p in re.split(r'[-–]', header)]
                route_str = ''
                day_str = ''
                for p in parts:
                    if 'Route' in p:
                        route_str = p
                    elif p in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
                        day_str = p

                # Extract dates
                matches = date_pattern.findall(text)
                parsed_dates = []
                for d_str, m_str in matches:
                    day_num = int(d_str)
                    month_num = months[m_str.lower()]
                    parsed_dates.append(f"2026-{month_num:02d}-{day_num:02d}")

                start_date = parsed_dates[0] if parsed_dates else '2026-01-05'

                # Extract stop table
                tables = page.extract_tables()
                for t in tables:
                    if not t:
                        continue
                    first_row = [str(c).lower() if c else '' for c in t[0]]
                    if any('village' in c for c in first_row) or any('stop' in c for c in first_row):
                        for row in t[1:]:
                            if not row or len(row) < 4:
                                continue
                            village = (row[0] or '').strip().replace('\n', ' ')
                            stop_loc = (row[1] or '').strip().replace('\n', ' ')
                            arr = (row[2] or '').strip()
                            dep = (row[3] or '').strip()
                            if not arr or not dep or not village:
                                continue

                            arr_fmt = normalise_time(arr)
                            dep_fmt = normalise_time(dep)

                            geo = geocode_dict.get(village)
                            geox = round(geo['longitude'], 6) if geo else ''
                            geoy = round(geo['latitude'], 6) if geo else ''
                            # Outcodes (e.g. LE14) do not match full UK postcode regex required by schema, so leave blank if not full postcode
                            raw_postcode = geo.get('postcode', '') if geo else ''
                            postcode = raw_postcode if len(raw_postcode.split()) == 2 else ''

                            address = f"{stop_loc}, {village}, Leicestershire"
                            stop_type = 'Public'

                            stops_list.append({
                                'Local authority': LOCAL_AUTHORITY,
                                'Local authority code': LOCAL_AUTHORITY_CODE,
                                'Mobile name': mobile_name,
                                'Route': route_str,
                                'Community': village,
                                'Stop': stop_loc,
                                'Address': address,
                                'Postcode': postcode,
                                'GeoX': geox,
                                'GeoY': geoy,
                                'Day': day_str,
                                'Type': stop_type,
                                'Arrival': arr_fmt,
                                'Departure': dep_fmt,
                                'Frequency': 'FREQ=WEEKLY;INTERVAL=3',
                                'Start': start_date,
                                'End': '',
                                'Exceptions': '',
                                'Timetable': timetable_url
                            })

    print(f"Extracted {len(stops_list)} stops for Leicestershire.")
    create_mobile_library_file('leicestershire.csv', stops_list)


if __name__ == '__main__':
    run()
