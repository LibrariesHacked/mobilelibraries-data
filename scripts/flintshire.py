"""Flintshire (Gwella Wales, formerly Aura): fortnightly mobile library.

Source: the "Mobile Library Timetable" table. The live page now returns 403 to
scripts, so this parses the Wayback Machine copy from 5 May 2023 (also kept in
raw/flintshire/historical/). Re-check against the live timetable when possible.
Output: data/flintshire.csv
"""

import re
from datetime import datetime

import bs4

import _common as c

AUTHORITY, CODE, SLUG = 'Flintshire', 'W06000005', 'flintshire'
LIVE_URL = 'https://gwella.wales/libraries'
SNAPSHOT_URL = ('https://web.archive.org/web/20230505051246id_/'
                'https://aura.wales/libraries/mobile-library-timetable/')
VEHICLE = 'Flintshire Mobile Library'

BBOX = (53.08, 53.36, -3.40, -2.90)
DEFAULT_CENTRE = (53.1674, -3.1419)
RENAMES = {'Green Lane Estate': 'Shotton', 'Higher Shotton': 'Shotton',
           'Calcoed': 'Holywell', 'Flint Mountain': 'Flint'}


def parse_timetable(html):
    """Return (route, day, area, location, arrival, departure) from the timetable table.

    Columns are Area | "11.15 / 11.45" | Location | list of due dates. The first
    due date gives the weekday and which fortnightly week the stop belongs to.
    """
    table = bs4.BeautifulSoup(html, 'html.parser').find('table')
    stops = []
    for row in (table.find_all('tr') if table else []):
        cells = [td.get_text(' ', strip=True) for td in row.find_all(['td', 'th'])]
        if len(cells) < 4 or not cells[0] or cells[0].lower() == 'area':
            continue
        times = re.search(r'(\d{1,2}[:.]\d{2})\s*/\s*(\d{1,2}[:.]\d{2})', cells[1])
        if not times:
            continue
        due = re.search(r'\b(Monday|Tuesday|Wednesday|Thursday|Friday)\s+May\s+(\d{1,2})\b', cells[3], re.I)
        day = due.group(1).title() if due else 'Tuesday'
        week = 1 if (int(due.group(2)) if due else 9) <= 12 else 2
        stops.append((f'Week {week} {day}', day, cells[0], cells[2],
                      c.to_24h(times.group(1)), c.to_24h(times.group(2))))
    return stops


def main():
    raw_dir = c.ROOT / 'raw' / SLUG / datetime.now().strftime('%Y-%m-%d')
    html = c.save_raw(raw_dir, 'mobile_library_timetable.html', SNAPSHOT_URL)
    (c.ROOT / 'raw' / SLUG / 'historical').mkdir(parents=True, exist_ok=True)
    (c.ROOT / 'raw' / SLUG / 'historical' / 'aura_mobile_library_timetable_2023.html').write_text(
        html, encoding='utf-8')

    cache, session, pc_cache, rows = c.load_geocache(), {}, {}, []
    for route, day, area, location, arrival, departure in parse_timetable(html):
        community = re.sub(r'\s*\(CH\d+\)', '', area).strip()
        lat, lng = c.geocode_place(AUTHORITY, community, location, cache, session,
                                   BBOX, AUTHORITY, DEFAULT_CENTRE, RENAMES)
        cache[f'{AUTHORITY}:{area}:{location}'.lower()] = (lat, lng)
        rows.append({
            'Local authority': AUTHORITY, 'Local authority code': CODE,
            'Mobile name': VEHICLE, 'Route': route, 'Community': area, 'Stop': location,
            'Address': c.format_address(location, area, 'Flintshire'),
            'Postcode': c.reverse_geocode_postcode(lat, lng, pc_cache),
            'GeoX': lng, 'GeoY': lat, 'Day': day, 'Type': 'Public',
            'Arrival': arrival, 'Departure': departure,
            'Frequency': 'FREQ=WEEKLY;INTERVAL=2',
            'Start': '2023-05-05', 'End': '2027-06-27',
            'Exceptions': '', 'Timetable': LIVE_URL,
        })

    c.save_geocache(cache)
    c.create_mobile_library_file(f'{SLUG}.csv', rows)
    c.validate_dataset(c.DATA_OUTPUT / f'{SLUG}.csv')
    c.register_vehicles(AUTHORITY, SLUG, {VEHICLE: 'Fortnightly service run by Gwella Wales (formerly Aura)'})
    c.update_service(CODE, has_mobile_service='Yes', status='Active Verified',
                     source_url=LIVE_URL, source_format='HTML Table (Wayback snapshot, May 2023)',
                     notes=f'Harvested {len(rows)} stops across fortnightly Week 1-2 routes. '
                           'Live timetable now blocks scripts; verify against the current one.')


if __name__ == '__main__':
    main()
