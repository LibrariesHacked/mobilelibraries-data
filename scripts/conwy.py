"""Conwy: 4-weekly mobile library routes 1-4.

Source: one HTML timetable page per route on conwy.gov.uk.
Output: data/conwy.csv
"""

import re
from datetime import datetime

import bs4

import _common as c

AUTHORITY, CODE, SLUG = 'Conwy', 'W06000003', 'conwy'
INDEX_URL = ('https://www.conwy.gov.uk/en/Resident/Libraries-Museums-and-Archives/'
             'Libraries/Mobile-library-routes/All-mobile-library-stops.aspx')
ROUTE_URL = ('https://www.conwy.gov.uk/en/Resident/Libraries-Museums-and-Archives/'
             'Libraries/Mobile-library-routes/Conwy-Mobile-Library-Route-{n}.aspx')
# Route number -> weekday the van runs that route.
ROUTES = {1: 'Tuesday', 2: 'Thursday', 3: 'Tuesday', 4: 'Thursday'}
VEHICLE = 'Conwy Mobile Library'

BBOX = (52.95, 53.35, -4.05, -3.45)  # rough extent of Conwy, to reject wrong-county matches
DEFAULT_CENTRE = (53.2825, -3.8295)
RENAMES = {'Llanfair TH': 'Llanfair Talhaiarn', 'Llanfihangel GM': 'Llanfihangel Glyn Myfyr',
           'Tal y Bont': 'Tal-y-bont', 'Betws y Coed': 'Betws-y-Coed'}


def parse_route(html, route_no):
    """Return (community, stop, arrival, departure) tuples from a route page's table."""
    stops = []
    for row in bs4.BeautifulSoup(html, 'html.parser').select('table tr'):
        cells = [td.get_text(' ', strip=True) for td in row.find_all(['td', 'th'])]
        if len(cells) < 3 or cells[0].lower() == 'village':
            continue
        times = re.findall(r'\d{1,2}[:.]\d{2}', cells[2])
        if len(times) == 2:
            stops.append((cells[0], cells[1], c.to_24h(times[0]), c.to_24h(times[1])))
    return stops


def main():
    raw_dir = c.ROOT / 'raw' / SLUG / datetime.now().strftime('%Y-%m-%d')
    c.save_raw(raw_dir, 'all_stops.html', INDEX_URL)
    cache, session, pc_cache, rows = c.load_geocache(), {}, {}, []

    for route_no, day in ROUTES.items():
        url = ROUTE_URL.format(n=route_no)
        html = c.save_raw(raw_dir, f'route_{route_no}.html', url)
        for community, stop, arrival, departure in parse_route(html, route_no):
            lat, lng = c.geocode_place(AUTHORITY, community, stop, cache, session,
                                       BBOX, AUTHORITY, DEFAULT_CENTRE, RENAMES)
            postcode = c.reverse_geocode_postcode(lat, lng, pc_cache)
            cache[f'{AUTHORITY}:{community}:{stop}'.lower()] = (lat, lng)
            rows.append({
                'Local authority': AUTHORITY, 'Local authority code': CODE,
                'Mobile name': VEHICLE, 'Route': f'Route {route_no}',
                'Community': community, 'Stop': stop,
                'Address': c.format_address(stop, community, 'Conwy'), 'Postcode': postcode,
                'GeoX': lng, 'GeoY': lat, 'Day': day, 'Type': 'Public',
                'Arrival': arrival, 'Departure': departure,
                'Frequency': 'FREQ=WEEKLY;INTERVAL=4',
                'Start': '2026-04-09', 'End': '2027-03-30',
                'Exceptions': 'Public holidays and Christmas', 'Timetable': url,
            })

    c.save_geocache(cache)
    c.create_mobile_library_file(f'{SLUG}.csv', rows)
    c.validate_dataset(c.DATA_OUTPUT / f'{SLUG}.csv')
    c.register_vehicles(AUTHORITY, SLUG, {VEHICLE: '4-weekly rural mobile library service'})
    c.update_service(CODE, has_mobile_service='Yes', status='Active Verified',
                     source_url=INDEX_URL, source_format='HTML Table',
                     notes=f'Harvested {len(rows)} stops across 4 routes on a 4-week cycle.')


if __name__ == '__main__':
    main()
