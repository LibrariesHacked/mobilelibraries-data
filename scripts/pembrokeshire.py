"""Pembrokeshire: 4-weekly village mobile library, routes A-H.

Source: a single HTML page on pembrokeshire.gov.uk with free-text route timetables.
Output: data/pembrokeshire.csv
"""

import re
from datetime import datetime

import bs4

import _common as c

AUTHORITY, CODE, SLUG = 'Pembrokeshire', 'W06000009', 'pembrokeshire'
URL = ('https://www.pembrokeshire.gov.uk/pembrokeshire-libraries/'
       'mobile-library-service-and-library-at-home')
VEHICLE = 'Pembrokeshire Mobile Library'

BBOX = (51.60, 52.12, -5.35, -4.50)
DEFAULT_CENTRE = (51.8017, -4.9708)
RENAMES = {'Glanrhyd (Penrallt)': 'Moylegrove', 'St. Dogmaels': 'St Dogmaels',
           'St.Florence': 'St Florence', 'St.Ishmaels': 'St Ishmaels',
           'Hayscastle Cross': 'Hayscastle', 'Simpson Cross': 'Roch',
           'Bwlch y Groes': 'Clydey', 'Blaenffos': 'Boncath'}

ROUTE_HEADER = re.compile(r'^([A-H]):\s*(.+)$')                    # "A: Brynberian - Glandwr"
DAY_HEADER = re.compile(r'^(Monday|Tuesday|Wednesday|Thursday|Friday)\s+\d+', re.I)
STOP_LINE = re.compile(r'^(.+?)\s+(\d{1,2}[:.]\d{2}\s*(?:am|pm)?)\s*[-\u2013]\s*'
                       r'(\d{1,2}[:.]\d{2}\s*(?:am|pm)?)$', re.I)  # "Spittal, The Green  9:15am - 9:45am"


def parse_page(html):
    """Walk the page text line by line, tracking the current route and weekday.

    Returns (route, day, community, stop, arrival, departure) tuples.
    """
    lines = [l.replace('\xa0', ' ').replace('\ufeff', '').strip()
             for l in bs4.BeautifulSoup(html, 'html.parser').get_text('\n').splitlines()]
    route = day = ''
    stops = []
    for line in filter(None, lines):
        if m := ROUTE_HEADER.match(line):
            route, day = f'Route {m.group(1)}: {m.group(2).strip()}', ''
        elif route and (m := DAY_HEADER.match(line)):
            day = m.group(1).title()
        elif route and day and (m := STOP_LINE.match(line)):
            place = m.group(1).strip()
            community, stop = [p.strip() for p in place.split(',', 1)] if ',' in place else (place, place)
            stops.append((route, day, community, stop, c.to_24h(m.group(2)), c.to_24h(m.group(3))))
    return stops


def main():
    raw_dir = c.ROOT / 'raw' / SLUG / datetime.now().strftime('%Y-%m-%d')
    html = c.save_raw(raw_dir, 'mobile_library.html', URL)
    cache, session, pc_cache, rows = c.load_geocache(), {}, {}, []

    for route, day, community, stop, arrival, departure in parse_page(html):
        lat, lng = c.geocode_place(AUTHORITY, community, stop, cache, session,
                                   BBOX, AUTHORITY, DEFAULT_CENTRE, RENAMES)
        cache[f'{AUTHORITY}:{community}:{stop}'.lower()] = (lat, lng)
        rows.append({
            'Local authority': AUTHORITY, 'Local authority code': CODE,
            'Mobile name': VEHICLE, 'Route': route, 'Community': community, 'Stop': stop,
            'Address': c.format_address(stop, community, 'Pembrokeshire'),
            'Postcode': c.reverse_geocode_postcode(lat, lng, pc_cache),
            'GeoX': lng, 'GeoY': lat, 'Day': day, 'Type': 'Public',
            'Arrival': arrival, 'Departure': departure,
            'Frequency': 'FREQ=WEEKLY;INTERVAL=4',
            'Start': '2026-10-01', 'End': '2026-12-24',
            'Exceptions': '', 'Timetable': URL,
        })

    c.save_geocache(cache)
    c.create_mobile_library_file(f'{SLUG}.csv', rows)
    c.validate_dataset(c.DATA_OUTPUT / f'{SLUG}.csv')
    c.register_vehicles(AUTHORITY, SLUG, {VEHICLE: '4-weekly village routes A-H'})
    c.update_service(CODE, has_mobile_service='Yes', status='Active Verified',
                     source_url=URL, source_format='HTML Timetable',
                     notes=f'Harvested {len(rows)} stops across 8 village routes (A-H) on a 4-week cycle.')


if __name__ == '__main__':
    main()
