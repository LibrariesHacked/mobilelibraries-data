"""Neath Port Talbot: 3-weekly mobile library, Weeks 1-3.

Source: one HTML page per week on npt.gov.uk (a table per weekday).
Output: data/neath_port_talbot.csv
"""

import re
from datetime import datetime

import bs4

import _common as c

AUTHORITY, CODE, SLUG = 'Neath Port Talbot', 'W06000012', 'neath_port_talbot'
INDEX_URL = 'https://www.npt.gov.uk/libraries/library-delivery-service/mobile-library-service/'
WEEK_URL = INDEX_URL + 'week-{n}-route/'
VEHICLE = 'Neath Port Talbot Mobile Library'
WEEKDAYS = {'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'}

BBOX = (51.50, 51.85, -3.95, -3.55)
DEFAULT_CENTRE = (51.6631, -3.8035)
RENAMES = {"Godre'r graig": 'Godrergraig', 'Gwaun Cae Gurwen': 'Gwaun-Cae-Gurwen'}


def parse_week(html):
    """Return (day, location, venue, arrival, departure) for every stop on a week page.

    Each weekday is an <h2> followed by a Location/Venue/Time table.
    """
    stops = []
    for heading in bs4.BeautifulSoup(html, 'html.parser').find_all('h2'):
        day = heading.get_text(' ', strip=True)
        container = heading.find_parent('div', class_='container')
        table = container.find('table') if day in WEEKDAYS and container else None
        for row in (table.find_all('tr') if table else []):
            cells = [td.get_text(' ', strip=True) for td in row.find_all(['td', 'th'])]
            if len(cells) < 3 or cells[0].lower() == 'location':
                continue
            times = re.findall(r'\d{1,2}[:.]\d{2}', cells[2])
            if len(times) == 2:
                arrival, departure = c.to_24h(times[0]), c.to_24h(times[1])
            elif cells[2].strip().upper() == 'PM':
                arrival, departure = '13:30', '15:00'  # "PM" = unspecified afternoon slot
            else:
                continue
            stops.append((day, cells[0], cells[1], arrival, departure))
    return stops


def stop_type(venue):
    """School-only visits aren't open to the public (the Briton Ferry layby is)."""
    venue = venue.lower()
    if 'former ynysmaerdy primary school' in venue:
        return 'Public'
    return 'Private' if 'school visit only' in venue or 'primary school' in venue else 'Public'


def main():
    raw_dir = c.ROOT / 'raw' / SLUG / datetime.now().strftime('%Y-%m-%d')
    c.save_raw(raw_dir, 'mobile_library_service.html', INDEX_URL)
    cache, session, pc_cache, rows = c.load_geocache(), {}, {}, []

    for week in (1, 2, 3):
        url = WEEK_URL.format(n=week)
        html = c.save_raw(raw_dir, f'week_{week}.html', url)
        for day, community, venue, arrival, departure in parse_week(html):
            lat, lng = c.geocode_place(AUTHORITY, community, venue, cache, session,
                                       BBOX, AUTHORITY, DEFAULT_CENTRE, RENAMES)
            cache[f'{AUTHORITY}:{community}:{venue}'.lower()] = (lat, lng)
            rows.append({
                'Local authority': AUTHORITY, 'Local authority code': CODE,
                'Mobile name': VEHICLE, 'Route': f'Week {week} {day}',
                'Community': community, 'Stop': venue,
                'Address': c.format_address(venue, community, 'Neath Port Talbot'),
                'Postcode': c.reverse_geocode_postcode(lat, lng, pc_cache),
                'GeoX': lng, 'GeoY': lat, 'Day': day, 'Type': stop_type(venue),
                'Arrival': arrival, 'Departure': departure,
                'Frequency': 'FREQ=WEEKLY;INTERVAL=3',
                'Start': '2026-11-03', 'End': '2026-12-24',
                'Exceptions': 'Bank holidays', 'Timetable': url,
            })

    c.save_geocache(cache)
    c.create_mobile_library_file(f'{SLUG}.csv', rows)
    c.validate_dataset(c.DATA_OUTPUT / f'{SLUG}.csv')
    c.register_vehicles(AUTHORITY, SLUG, {VEHICLE: '3-weekly mobile library service'})
    c.update_service(CODE, has_mobile_service='Yes', status='Active Verified',
                     source_url=INDEX_URL, source_format='HTML Table',
                     notes=f'Harvested {len(rows)} stops across Week 1-3 routes on a 3-week cycle.')


if __name__ == '__main__':
    main()
