"""
Dedicated Lancashire Mobile Library Extractor.
Extracts all 498 official pre-geocoded mobile library stops from Lancashire County
Council's cached ArcGIS FeatureServer JSON in WGS84 coordinates, maps them to
schema-librarydata/mobile-library-stops.json, and writes data/lancashire.csv.
"""

import json
from datetime import datetime
from pathlib import Path

from _common import create_mobile_library_file
from geocoder import Geocoder

RAW_JSON = Path(__file__).resolve().parent.parent / 'raw' / 'lancashire' / '2026-11-18' / 'arcgis_features.json'
LOCAL_AUTHORITY = 'Lancashire'
LOCAL_AUTHORITY_CODE = 'E10000017'
TIMETABLE_URL = 'https://www.lancashire.gov.uk/libraries/mobile-library/'


def format_time_num(val):
    """Format an integer or string HHMM time (e.g. 930, 1415) as HH:MM, defaulting to '09:00' if falsy."""
    if not val:
        return '09:00'
    val_str = str(val).zfill(4)
    hours = val_str[:2]
    minutes = val_str[2:]
    return f"{int(hours):02d}:{int(minutes):02d}"


def run():
    """Load cached Lancashire ArcGIS JSON features, map them to schema rows, update the geocache, and write data/lancashire.csv."""
    geocoder = Geocoder()
    data = json.loads(RAW_JSON.read_text(encoding='utf-8'))
    features = data.get('features', [])

    stops = []
    print(f"Processing {len(features)} stops from Lancashire ArcGIS Service...")

    for f in features:
        attrs = f.get('attributes', {})
        geom = f.get('geometry', {})

        lon = geom.get('x', '')
        lat = geom.get('y', '')
        geox = round(lon, 6) if lon else ''
        geoy = round(lat, 6) if lat else ''

        mobile_code = attrs.get('Mobile', 'Mobile')
        base_lib = attrs.get('BaseLibrary', '')
        mobile_name = f"{mobile_code} ({base_lib})" if base_lib else mobile_code

        route_num = attrs.get('Route', 1)
        day = attrs.get('WeekDay') or ''
        if not day and attrs.get('DayOfWeekTXT'):
            day = attrs.get('DayOfWeekTXT').split('-')[-1].strip()
        if not day and attrs.get('WeekDayNumber'):
            day_map = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday', 7: 'Sunday'}
            day = day_map.get(attrs.get('WeekDayNumber'), 'Monday')
        route_name = f"Route {route_num} - {day}"

        locality = attrs.get('Locality', '')
        district = attrs.get('District', '')
        community = locality or district or 'Lancashire'

        roadname = attrs.get('Roadname', '')
        stop_details = attrs.get('StopDetails', '')
        stop_name = roadname or (stop_details.split(':')[-1].strip() if ':' in stop_details else stop_details) or 'Stop'

        # Lancashire's ArcGIS schema stores some stop postcodes in 'Hazards'; require full outward + inward pair
        postcode_hint = str(attrs.get('Hazards') or '').strip()
        postcode = postcode_hint if len(postcode_hint.split()) == 2 else ''

        arr_num = attrs.get('VisitStartTime')
        dep_num = attrs.get('VisitEndTime')
        arr = format_time_num(arr_num)
        dep = format_time_num(dep_num)

        # 3-week rota
        frequency = 'FREQ=WEEKLY;INTERVAL=3'

        # KnownVisit timestamp if available (ArcGIS dates are epoch milliseconds)
        known_ms = attrs.get('KnownVisit')
        if known_ms:
            start_date = datetime.fromtimestamp(known_ms / 1000.0).strftime('%Y-%m-%d')
        else:
            start_date = '2026-01-05'

        address = f"{stop_name}, {community}, {district}, Lancashire".strip(', ')

        # Cache coordinates into persistent geocache
        if geox and geoy:
            geocoder.remember_stop(LOCAL_AUTHORITY, community, stop_name, geox, geoy, postcode, 'lancashire_arcgis')

        stops.append({
            'Local authority': LOCAL_AUTHORITY,
            'Local authority code': LOCAL_AUTHORITY_CODE,
            'Mobile name': mobile_name,
            'Route': route_name,
            'Community': community,
            'Stop': stop_name,
            'Address': address,
            'Postcode': postcode,
            'GeoX': geox,
            'GeoY': geoy,
            'Day': day,
            'Type': 'Public',
            'Arrival': arr,
            'Departure': dep,
            'Frequency': frequency,
            'Start': start_date,
            'End': '',
            'Exceptions': '',
            'Timetable': TIMETABLE_URL
        })

    geocoder.save_caches()
    print(f"Extracted {len(stops)} stops for Lancashire.")
    create_mobile_library_file('lancashire.csv', stops)


if __name__ == '__main__':
    run()
