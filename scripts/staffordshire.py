"""
Dedicated Staffordshire Mobile Library Extractor.
Parses live community stop tables across all 10 route schedules (Week 1 and Week 2),
resolves coordinates via Geocoder reference cache, and writes schema-compliant data.
"""

import re
from pathlib import Path
from bs4 import BeautifulSoup

from _common import create_mobile_library_file
from geocoder import Geocoder

HTML_DIR = Path(__file__).resolve().parent.parent / 'raw' / 'staffordshire' / '2026-11-18' / 'routes'
LOCAL_AUTHORITY = 'Staffordshire'
LOCAL_AUTHORITY_CODE = 'E10000028'
BASE_URL = 'https://www.staffordshire.gov.uk/libraries/mobile-libraries'

TIME_RANGE_RE = re.compile(r'(\d{1,2}):(\d{2})\s*(am|pm)\s*to\s*(\d{1,2}):(\d{2})\s*(am|pm)', re.IGNORECASE)


def parse_ampm(h_str, m_str, meridiem):
    hours = int(h_str)
    minutes = int(m_str)
    mer = meridiem.upper()
    if mer == 'PM' and hours != 12:
        hours += 12
    elif mer == 'AM' and hours == 12:
        hours = 0
    return f"{hours:02d}:{minutes:02d}"


def run():
    geocoder = Geocoder()
    stops = []

    files = sorted(HTML_DIR.glob('*.html'))
    print(f"Parsing {len(files)} route files for Staffordshire...")

    for fpath in files:
        slug = fpath.stem
        # e.g. mobile-1-mondays-week-1
        m_mob = 'Mobile 2' if 'mobile-2' in slug else 'Mobile 1'
        m_week = 'Week 2' if 'week-2' in slug else 'Week 1'

        day_name = 'Monday'
        for d in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
            if d.lower() in slug:
                day_name = d
                break

        route_name = f"{m_week} - {day_name}"
        html = fpath.read_text(encoding='utf-8')
        soup = BeautifulSoup(html, 'html.parser')

        table = soup.find('table')
        if not table:
            continue

        for tr in table.find_all('tr')[1:]:
            cols = [c.get_text(strip=True) for c in tr.find_all(['td', 'th'])]
            if len(cols) < 3:
                continue

            community = cols[0]
            location = cols[1]
            time_raw = cols[2]

            m_time = TIME_RANGE_RE.search(time_raw)
            if m_time:
                arr = parse_ampm(m_time.group(1), m_time.group(2), m_time.group(3))
                dep = parse_ampm(m_time.group(4), m_time.group(5), m_time.group(6))
            else:
                arr = '09:30'
                dep = '10:00'

            geo = geocoder.resolve(LOCAL_AUTHORITY, community, location)
            geox = geo.get('geox', '')
            geoy = geo.get('geoy', '')
            postcode = geo.get('postcode', '')

            address = f"{location}, {community}, Staffordshire".strip(', ')

            stops.append({
                'Local authority': LOCAL_AUTHORITY,
                'Local authority code': LOCAL_AUTHORITY_CODE,
                'Mobile name': m_mob,
                'Route': route_name,
                'Community': community,
                'Stop': location,
                'Address': address,
                'Postcode': postcode,
                'GeoX': geox,
                'GeoY': geoy,
                'Day': day_name,
                'Type': 'Public',
                'Arrival': arr,
                'Departure': dep,
                'Frequency': 'FREQ=WEEKLY;INTERVAL=2',
                'Start': '2026-01-05',
                'End': '',
                'Exceptions': '',
                'Timetable': f"{BASE_URL}/{slug}"
            })

    geocoder.save_caches()
    print(f"Extracted {len(stops)} stops for Staffordshire.")
    create_mobile_library_file('staffordshire.csv', stops)


if __name__ == '__main__':
    run()
