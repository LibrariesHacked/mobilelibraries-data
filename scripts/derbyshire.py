"""
Dedicated Derbyshire Mobile Library Timetable Parser.
Parses 4-week rotating timetables (North & South mobiles) from official PDF,
resolves coordinates via Geocoder reference cache, and writes schema-compliant data.
"""

import csv
import re
from pathlib import Path
import pdfplumber

from _common import create_mobile_library_file
from geocoder import Geocoder

RAW_PDF = Path(__file__).resolve().parent.parent / 'raw' / 'derbyshire' / '2026-11-18' / 'mobile-library-routes.pdf'
TIMETABLE_URL = 'https://www.derbyshire.gov.uk/leisure/libraries/services/mobile-libraries/mobile-libraries.aspx'
LOCAL_AUTHORITY = 'Derbyshire'
LOCAL_AUTHORITY_CODE = 'E10000007'

TIME_AMPM_RE = re.compile(r'(\d{1,2}):(\d{2})\s*(AM|PM)', re.IGNORECASE)


def parse_ampm_to_24h(time_str):
    m = TIME_AMPM_RE.search(time_str.strip())
    if not m:
        return ''
    hours = int(m.group(1))
    minutes = int(m.group(2))
    meridiem = m.group(3).upper()

    # Sometimes PDF has typo like '13:20 PM' which is already 24h
    if hours > 12:
        return f"{hours:02d}:{minutes:02d}"

    if meridiem == 'PM' and hours != 12:
        hours += 12
    elif meridiem == 'AM' and hours == 12:
        hours = 0
    return f"{hours:02d}:{minutes:02d}"


def run():
    geocoder = Geocoder()
    stops = []

    with pdfplumber.open(RAW_PDF) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for t in tables:
                for row in t:
                    cells = [c.strip() for c in row if c and c.strip()]
                    # Stop row format: ['2', 'Ambergate (S)', 'Railway Station Car Park', 'Tuesday', '10:45 AM', '12:15 PM', ...]
                    if len(cells) >= 6 and ('AM' in cells[4] or 'PM' in cells[4]):
                        week_num = cells[0]
                        place_raw = cells[1]
                        location = cells[2]
                        day = cells[3]
                        arr_raw = cells[4]
                        dep_raw = cells[5]

                        # Detect mobile from place tag e.g. 'Ambergate (S)' or 'Ashover (N)'
                        mobile_name = 'South Mobile (Long Eaton)' if '(S)' in place_raw else ('North Mobile (Buxton)' if '(N)' in place_raw else 'Mobile Library')
                        community = re.sub(r'\s*\([SN]\)', '', place_raw).strip()
                        route = f"Week {week_num} - {day}"

                        arr = parse_ampm_to_24h(arr_raw)
                        dep = parse_ampm_to_24h(dep_raw)

                        # Geocode
                        geo = geocoder.resolve(LOCAL_AUTHORITY, community, location)
                        geox = geo.get('geox', '')
                        geoy = geo.get('geoy', '')
                        postcode = geo.get('postcode', '')

                        address = f"{location}, {community}, Derbyshire"

                        stops.append({
                            'Local authority': LOCAL_AUTHORITY,
                            'Local authority code': LOCAL_AUTHORITY_CODE,
                            'Mobile name': mobile_name,
                            'Route': route,
                            'Community': community,
                            'Stop': location,
                            'Address': address,
                            'Postcode': postcode,
                            'GeoX': geox,
                            'GeoY': geoy,
                            'Day': day,
                            'Type': 'Public',
                            'Arrival': arr,
                            'Departure': dep,
                            'Frequency': 'FREQ=WEEKLY;INTERVAL=4',
                            'Start': '2026-09-01',
                            'End': '2026-12-31',
                            'Exceptions': '',
                            'Timetable': TIMETABLE_URL
                        })

    geocoder.save_caches()
    print(f"Extracted {len(stops)} stops for Derbyshire.")
    create_mobile_library_file('derbyshire.csv', stops)


if __name__ == '__main__':
    run()
