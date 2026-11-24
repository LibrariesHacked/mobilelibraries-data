"""
Dedicated Lincolnshire Mobile Library Timetable Parser (Lincolnshire County Council).
Parses community stop timetables across all 20 route PDF files (Better/GLL partnership,
sourced from https://www.better.org.uk/library/lincolnshire/accessibility/mobile-library),
resolves coordinates via Geocoder reference cache, and writes schema-compliant data to data/lincolnshire.csv.
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

# Matches day name, optional 4-weekly rota number, and 24-hour arrival-departure times
TIME_RE = re.compile(
    r'(Monday|Tuesday|Wednesday|Thursday|Thurs|Friday|Saturday|Sunday|Weds)\s*([0-9&]+)?\s+(\d{1,2}[:.]\d{2})\s*[-–]\s*(\d{1,2}[:.]\d{2})',
    re.IGNORECASE
)


def normalise_time(t_str):
    """Zero-pad the hour in a 'H:MM' or 'H.MM' time string to 'HH:MM'."""
    t_str = t_str.strip().replace(' ', '').replace('.', ':')
    if ':' in t_str:
        h, m = t_str.split(':')
        return f"{int(h):02d}:{int(m):02d}"
    return t_str


def run():
    """Extract stop schedules from cached Lincolnshire PDFs, geocode stops, and write data/lincolnshire.csv."""
    geocoder = Geocoder()
    stops = []

    for pdf_file in sorted(PDF_DIR.glob('*.pdf')):
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                # Find distinct column start positions
                x_cols = sorted(set([round(r['x0'], 1) for r in page.rects if r['height'] > 20]))
                distinct_x = []
                for x in x_cols:
                    if not distinct_x or x - distinct_x[-1] > 2:
                        distinct_x.append(x)
                if len(distinct_x) < 4:
                    continue
                x_loc_0, x_svc_0, x_time_0, x_date_0 = distinct_x[:4]

                # Find cells in Day/Time column
                time_cells = [r for r in page.rects if abs(r['x0'] - x_time_0) <= 2 and r['height'] > 20]
                time_cells.sort(key=lambda r: r['top'])

                for tc in time_cells:
                    t_top, t_bot = tc['top'], tc['bottom']
                    time_words = [w['text'] for w in page.extract_words() if t_top - 2 <= w['top'] <= t_bot + 2 and x_time_0 - 2 <= w['x0'] <= x_date_0]
                    time_str = ' '.join(time_words)

                    m = TIME_RE.search(time_str)
                    if not m:
                        continue

                    day = m.group(1).capitalize()
                    if day.startswith('Thurs'):
                        day = 'Thursday'
                    elif day.startswith('Weds'):
                        day = 'Wednesday'

                    rota_num = m.group(2) or '1'
                    arr_str = normalise_time(m.group(3))
                    dep_str = normalise_time(m.group(4))

                    svc_words = [w['text'] for w in page.extract_words() if t_top - 2 <= w['top'] <= t_bot + 2 and x_svc_0 - 2 <= w['x0'] <= x_time_0]
                    svc_str = ' '.join(svc_words)

                    loc_words = [w['text'] for w in page.extract_words() if t_top - 2 <= w['top'] <= t_bot + 2 and x_loc_0 - 2 <= w['x0'] <= x_svc_0]
                    loc_str = ' '.join(loc_words)

                    # Mobile vehicle
                    mobile_name = 'Mobile Library'
                    if 'South' in svc_str:
                        mobile_name = 'Mobile Library South'
                    elif 'North' in svc_str:
                        mobile_name = 'Mobile Library North'
                    elif 'East' in svc_str:
                        mobile_name = 'Mobile Library East'

                    # Clean location string
                    loc_clean = loc_str.replace('–', '-').replace('—', '-')
                    loc_parts = [p.strip() for p in loc_clean.split('-', 1)]
                    community = loc_parts[0] if loc_parts else 'Lincolnshire'
                    stop_loc = loc_parts[1] if len(loc_parts) > 1 and loc_parts[1] else community

                    route_name = f"{mobile_name} - {day} {rota_num}"

                    # Geocode
                    geo = geocoder.resolve(LOCAL_AUTHORITY, community, stop_loc)
                    geox = geo.get('geox', '')
                    geoy = geo.get('geoy', '')
                    postcode = geo.get('postcode', '')

                    address = f"{stop_loc}, {community}, Lincolnshire".strip(', ')

                    # Handle Frequency: check if biweekly e.g. '1&3' or '2&4'
                    if '&' in rota_num:
                        frequency = 'FREQ=WEEKLY;INTERVAL=2'
                    else:
                        frequency = 'FREQ=WEEKLY;INTERVAL=4'

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
                        'Frequency': frequency,
                        'Start': '2026-01-05',
                        'End': '',
                        'Exceptions': '',
                        'Timetable': TIMETABLE_URL
                    })

    geocoder.save_caches()

    # Disambiguate parallel runs in Lincolnshire:
    # When a synthesized route has overlapping stop time windows, it represents multiple
    # distinct vehicle circuits operating in the sector. Separate them into Route 1, Route 2, etc.
    from collections import defaultdict

    def to_min(t_str):
        if not t_str or ':' not in t_str:
            return 0
        h, m = t_str.split(':')
        return int(h) * 60 + int(m)

    by_route = defaultdict(list)
    for s in stops:
        by_route[s['Route']].append(s)

    final_stops = []
    for r_name, r_stops in by_route.items():
        r_stops.sort(key=lambda s: to_min(s['Arrival']))
        circuits = []
        for s in r_stops:
            s_arr = to_min(s['Arrival'])
            placed = False
            for c in circuits:
                last_dep = to_min(c[-1]['Departure'])
                if s_arr >= last_dep:
                    c.append(s)
                    placed = True
                    break
            if not placed:
                circuits.append([s])

        if len(circuits) == 1:
            final_stops.extend(r_stops)
        else:
            for idx, c in enumerate(circuits, 1):
                for s in c:
                    s['Route'] = f"{r_name} Route {idx}"
                    final_stops.append(s)

    print(f"Extracted {len(final_stops)} stops across {len(set(s['Route'] for s in final_stops))} routes for Lincolnshire.")
    create_mobile_library_file('lincolnshire.csv', final_stops)


if __name__ == '__main__':
    run()
