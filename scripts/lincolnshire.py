"""
Dedicated Lincolnshire Mobile Library Timetable Parser.
Parses community stop timetables across all 20 route PDF files (Better/GLL partnership),
resolves coordinates via Geocoder reference cache, and writes schema-compliant data.
"""

import re
from pathlib import Path
import pdfplumber

from _common import create_mobile_library_file
from geocoder import Geocoder

PDF_DIR = Path(__file__).resolve().parent.parent / 'raw' / 'lincolnshire' / '2026-11-18' / 'pdfs'
TIMETABLE_URL = 'https://www.better.org.uk/library/lincolnshire/accessibility/mobile-library'
LOCAL_AUTHORITY = 'Lincolnshire'
LOCAL_AUTHORITY_CODE = 'E10000019'

TIME_RE = re.compile(
    r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*(\d+)?\s+(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})',
    re.IGNORECASE
)


def normalise_time(t_str):
    t_str = t_str.strip().replace(' ', '')
    if ':' in t_str:
        h, m = t_str.split(':')
        return f"{int(h):02d}:{int(m):02d}"
    return t_str


def run():
    geocoder = Geocoder()
    stops = []

    for pdf_file in sorted(PDF_DIR.glob('*.pdf')):
        with pdfplumber.open(pdf_file) as pdf:
            current_location_label = ''
            for page in pdf.pages:
                tables = page.extract_tables()
                for t in tables:
                    for row in t:
                        cells = [c.strip().replace('\n', ' ') for c in row if c and c.strip()]
                        if not cells:
                            continue

                        # Check if first cell has location name e.g. 'Aisby - Village Green'
                        first_cell = cells[0]
                        if '-' in first_cell and not any(m in first_cell for m in ['Mobile', 'Library', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']):
                            current_location_label = first_cell

                        # Find the time and mobile information in row
                        row_text = ' '.join(cells)
                        m = TIME_RE.search(row_text)
                        if m:
                            day = m.group(1).capitalize()
                            rota_num = m.group(2) or '1'
                            arr_str = normalise_time(m.group(3))
                            dep_str = normalise_time(m.group(4))

                            # Mobile vehicle
                            mobile_name = 'Mobile Library'
                            if 'South' in row_text:
                                mobile_name = 'Mobile Library South'
                            elif 'North' in row_text:
                                mobile_name = 'Mobile Library North'
                            elif 'East' in row_text:
                                mobile_name = 'Mobile Library East'

                            # Split location into Community and Stop
                            loc_parts = [p.strip() for p in current_location_label.split('-', 1)]
                            community = loc_parts[0] if loc_parts else 'Lincolnshire'
                            stop_loc = loc_parts[1] if len(loc_parts) > 1 and loc_parts[1] else (community or 'Village Stop')

                            route_name = f"{mobile_name} - {day} {rota_num}"

                            # Geocode
                            geo = geocoder.resolve(LOCAL_AUTHORITY, community, stop_loc)
                            geox = geo.get('geox', '')
                            geoy = geo.get('geoy', '')
                            postcode = geo.get('postcode', '')

                            address = f"{stop_loc}, {community}, Lincolnshire".strip(', ')

                            stops.append({
                                'Local authority': LOCAL_AUTHORITY,
                                'Local authority code': LOCAL_AUTHORITY_CODE,
                                'Mobile name': mobile_name,
                                'Route': route_name,
                                'Community': community,
                                'Stop': stop_loc,
                                'Address': address,
                                'Postcode': postcode,
                                'GeoX': geox,
                                'GeoY': geoy,
                                'Day': day,
                                'Type': 'Public',
                                'Arrival': arr_str,
                                'Departure': dep_str,
                                'Frequency': 'FREQ=WEEKLY;INTERVAL=4',
                                'Start': '2026-01-05',
                                'End': '',
                                'Exceptions': '',
                                'Timetable': TIMETABLE_URL
                            })

    geocoder.save_caches()
    print(f"Extracted {len(stops)} stops for Lincolnshire.")
    create_mobile_library_file('lincolnshire.csv', stops)


if __name__ == '__main__':
    run()
