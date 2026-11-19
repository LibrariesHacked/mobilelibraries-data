"""
Dedicated Bath and North East Somerset (B&NES) Mobile Library Extractor.
Pulls recurring mobile library timetables and venues from the live WordPress /
Tribe Events calendar REST API, geocodes stops via Geocoder reference cache,
and outputs schema-compliant mobile library stops.
"""

import html
import json
from datetime import datetime
from pathlib import Path

from _common import create_mobile_library_file
from geocoder import Geocoder

RAW_JSON = Path(__file__).resolve().parent.parent / 'raw' / 'bath_and_north_east_somerset' / '2026-11-18' / 'tribe_events.json'
LOCAL_AUTHORITY = 'Bath and North East Somerset'
LOCAL_AUTHORITY_CODE = 'E06000022'
TIMETABLE_URL = 'https://baneslibraries.co.uk/visit-our-libraries/mobile-library/'


def run():
    """Deduplicate B&NES Tribe Events JSON stops, geocode them, and write data/bath_and_north_east_somerset.csv."""
    geocoder = Geocoder()
    events = json.loads(RAW_JSON.read_text(encoding='utf-8'))

    stops_dict = {}

    for e in events:
        title = html.unescape(e.get('title', '')).strip()
        venue = e.get('venue', {})
        venue_name = html.unescape(venue.get('venue', '')).strip()
        addr = venue.get('address', '').strip()
        city = venue.get('city', '').strip()
        zip_code = venue.get('zip', '').strip()

        start_dt = e.get('start_date')
        end_dt = e.get('end_date')
        if not start_dt or not end_dt:
            continue

        dt = datetime.strptime(start_dt, '%Y-%m-%d %H:%M:%S')
        end_obj = datetime.strptime(end_dt, '%Y-%m-%d %H:%M:%S')

        day_name = dt.strftime('%A')
        arr = dt.strftime('%H:%M')
        dep = end_obj.strftime('%H:%M')

        # Clean location details
        # e.g. title: "Manor Park, Writhlington"
        if ',' in title:
            stop_name, comm_name = [p.strip() for p in title.split(',', 1)]
        else:
            stop_name = venue_name or title
            comm_name = city or title

        key = (comm_name, stop_name, day_name, arr, dep)
        if key not in stops_dict:
            stops_dict[key] = {
                'community': comm_name,
                'stop': stop_name,
                'address': f"{addr}, {comm_name}, Bath & North East Somerset".strip(', '),
                # Require full two-part UK postcode (outcode + incode)
                'postcode': zip_code if len(zip_code.split()) == 2 else '',
                'day': day_name,
                'arrival': arr,
                'departure': dep,
                'start': dt.strftime('%Y-%m-%d')
            }

    stops = []
    print(f"Extracted {len(stops_dict)} distinct stops for B&NES.")

    for item in sorted(stops_dict.values(), key=lambda x: (x['day'], x['arrival'])):
        comm = item['community']
        stop_name = item['stop']
        pc = item['postcode']

        # Geocode via reference cache / API
        geo = geocoder.resolve(LOCAL_AUTHORITY, comm, stop_name, postcode=pc)
        geox = geo.get('geox', '')
        geoy = geo.get('geoy', '')
        resolved_pc = geo.get('postcode') or pc

        stops.append({
            'Local authority': LOCAL_AUTHORITY,
            'Local authority code': LOCAL_AUTHORITY_CODE,
            'Mobile name': 'Mobile Library',
            'Route': f"Fortnightly - {item['day']}",
            'Community': comm,
            'Stop': stop_name,
            'Address': item['address'],
            'Postcode': resolved_pc if len(resolved_pc.split()) == 2 else '',
            'GeoX': geox,
            'GeoY': geoy,
            'Day': item['day'],
            'Type': 'Public',
            'Arrival': item['arrival'],
            'Departure': item['departure'],
            'Frequency': 'FREQ=WEEKLY;INTERVAL=2',
            'Start': item['start'],
            'End': '',
            'Exceptions': '',
            'Timetable': TIMETABLE_URL
        })

    geocoder.save_caches()
    create_mobile_library_file('bath_and_north_east_somerset.csv', stops)
    print(f"Saved {len(stops)} stops to data/bath_and_north_east_somerset.csv")


if __name__ == '__main__':
    run()
