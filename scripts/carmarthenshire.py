"""Carmarthenshire: mobile library, one web page per stop.

Source: an index page listing ~60 stops; each stop page shows its next visit
(date, weekday, times), location and route. Stops with no upcoming visit are
archived to history/ rather than published as active.
Output: data/carmarthenshire.csv
"""

import re
from datetime import datetime

import bs4

import _common as c

AUTHORITY, CODE, SLUG = 'Carmarthenshire', 'W06000010', 'carmarthenshire'
DOMAIN = 'https://www.carmarthenshire.gov.wales'
INDEX_PATH = '/home/council-services/libraries-archives/mobile-libraries/'
VEHICLE = 'Carmarthenshire Mobile Library'

BBOX = (51.65, 52.15, -4.65, -3.70)
DEFAULT_CENTRE = (51.8576, -4.3121)
RENAMES = {'Crosshands': 'Cross Hands', 'Banc y felin': 'Bancyfelin', 'Mynyddygarreg': 'Mynydd-y-garreg'}
# "Llansteffan Square", "Llanybri Hen Gapel", "Llanpumsaint 1" -> the village name only.
SUFFIX = re.compile(r'\s+(Square|Y Wesle|Ger-Y-Capel|Hall|Ger Y Marbell|Hen Gapel|1)$', re.I)
VISIT = re.compile(r'(\d{2}/\d{2}/\d{4})\s*~\s*(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
                   r'\s+(\d{1,2}[:.]\d{2})\s*[-\u2013]\s*(\d{1,2}[:.]\d{2})', re.I)


def parse_stop_page(html, url):
    """Parse one stop page into a dict, or None if it isn't a stop page.

    `active` is False when no upcoming visit is listed. For active stops the
    interval is inferred from the gap between the first two listed visits
    (defaulting to 3 weeks).
    """
    content = bs4.BeautifulSoup(html, 'html.parser')
    page = content.find(id='content') or content
    heading = page.find('h1')
    dates = page.find('div', class_='mobileLibraryDates')
    if not heading or not dates:
        return None

    # The <h1> reads "<Community>  <n>: Village - Village - Village" (n = route number).
    sub = heading.find('span', class_='small')
    route = f"Route {' '.join(sub.get_text(' ', strip=True).split())}" if sub else 'Route 1'
    if sub:
        sub.extract()
    community = ' '.join(heading.get_text(' ', strip=True).split())

    text = '\n'.join(' '.join(p.get_text(' ', strip=True).split()) for p in dates.find_all(['p', 'li']))
    stop = community
    for p in dates.find_all('p'):
        line = ' '.join(p.get_text(' ', strip=True).split())
        if 'Location:' in line:
            location = re.sub(r'\s*View location.*$', '', line.split('Location:', 1)[1], flags=re.I).strip()
            stop = location.split(' - ', 1)[-1].strip() or stop

    visit = VISIT.search(text)
    base = {'route': route, 'community': community, 'stop': stop, 'url': url}
    if not visit:
        return {**base, 'active': False}

    listed = [datetime.strptime(d, '%d/%m/%Y') for d in re.findall(r'(\d{2}/\d{2}/\d{4})\s*~', text)]
    gap_weeks = abs((listed[1] - listed[0]).days) // 7 if len(listed) > 1 else 3
    return {**base, 'active': True, 'day': visit.group(2).title(),
            'arrival': c.to_24h(visit.group(3)), 'departure': c.to_24h(visit.group(4)),
            'interval': gap_weeks if gap_weeks >= 1 else 3, 'start': listed[0].strftime('%Y-%m-%d')}


def locate(community, stop, cache, session, pc_cache):
    """Return (lat, lng, postcode) for a stop, updating the shared cache."""
    village = SUFFIX.sub('', community).strip()
    lat, lng = c.geocode_place(AUTHORITY, village, stop, cache, session,
                               BBOX, AUTHORITY, DEFAULT_CENTRE, RENAMES)
    cache[f'{AUTHORITY}:{community}:{stop}'.lower()] = (lat, lng)
    return lat, lng, c.reverse_geocode_postcode(lat, lng, pc_cache)


def main():
    today = datetime.now().strftime('%Y-%m-%d')
    raw_dir = c.ROOT / 'raw' / SLUG / today
    index = bs4.BeautifulSoup(c.save_raw(raw_dir, 'index.html', DOMAIN + INDEX_PATH), 'html.parser')
    paths = sorted({a['href'] for a in index.find_all('a', href=True)
                    if a['href'].startswith(INDEX_PATH) and a['href'].rstrip('/') != INDEX_PATH.rstrip('/')})
    print(f'Found {len(paths)} stop pages')

    cache, session, pc_cache = c.load_geocache(), {}, {}
    rows, unscheduled = [], []
    for path in paths:
        url = DOMAIN + path
        try:
            html = c.save_raw(raw_dir / 'stops', path.rstrip('/').split('/')[-1] + '.html', url)
        except Exception as error:  # a single unreachable page shouldn't abort the run
            print(f'  skipped {url}: {error}')
            continue
        stop = parse_stop_page(html, url)
        if not stop:
            continue
        lat, lng, postcode = locate(stop['community'], stop['stop'], cache, session, pc_cache)
        common = {'Local authority': AUTHORITY, 'Local authority code': CODE, 'Mobile name': VEHICLE,
                  'Route': stop['route'], 'Community': stop['community'], 'Stop': stop['stop'],
                  'Address': c.format_address(stop['stop'], stop['community'], 'Carmarthenshire'),
                  'Postcode': postcode, 'GeoX': lng, 'GeoY': lat, 'Type': 'Public'}
        if stop['active']:
            rows.append({**common, 'Day': stop['day'], 'Arrival': stop['arrival'],
                         'Departure': stop['departure'],
                         'Frequency': f"FREQ=WEEKLY;INTERVAL={stop['interval']}",
                         'Start': stop['start'], 'End': '2027-03-31',
                         'Exceptions': '', 'Timetable': stop['url']})
        else:
            unscheduled.append({**common, 'Day': '', 'Arrival': '', 'Departure': '',
                                'Frequency': 'FREQ=WEEKLY;INTERVAL=3', 'Start': '',
                                'Dataset slug': SLUG, 'Archive source': stop['url'],
                                'Status': 'Suspended / Unscheduled'})

    print(f'{len(rows)} active, {len(unscheduled)} unscheduled stops')
    c.save_geocache(cache)
    c.archive_stops(unscheduled)
    c.create_mobile_library_file(f'{SLUG}.csv', rows)
    c.validate_dataset(c.DATA_OUTPUT / f'{SLUG}.csv')
    c.register_vehicles(AUTHORITY, SLUG, {VEHICLE: '3-weekly rural mobile library with Wi-Fi hotspot'})
    c.update_service(CODE, has_mobile_service='Yes', status='Active Verified',
                     source_url=DOMAIN + INDEX_PATH, source_format='HTML Stop Pages',
                     notes=f'Harvested {len(rows)} active stops ({len(unscheduled)} unscheduled '
                           'archived to history) across 3-weekly routes.')


if __name__ == '__main__':
    main()
