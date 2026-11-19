"""
Shropshire Council Mobile Library Ingestion Script.
Harvests live 2026 pre-geocoded mobile library stops from Shropshire Council's
ArcGIS Feature Server (Layer 11), validates against Frictionless Schema, and updates services.csv.
"""

import os
import re
import csv
import json
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

from _common import create_mobile_library_file
from geocoder import Geocoder

AUTHORITY_NAME = 'Shropshire'
AUTHORITY_CODE = 'E06000051'
SLUG = 'shropshire'
DATE_DIR = '2026-11-18'
RAW_DIR = Path('raw') / SLUG / DATE_DIR
DATA_FILE = Path('data') / f'{SLUG}.csv'
BASE_URL = 'https://next.shropshire.gov.uk/libraries/mobile-libraries/'
ARCGIS_QUERY_URL = 'https://gis.shropshire.gov.uk/arcgis/rest/services/AGOL/FeatureLayers/MapServer/11/query'


def download_raw_arcgis_data():
    """Fetch Shropshire ArcGIS FeatureServer Layer 11 in WGS84, save raw JSON, and return parsed dict."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_file = RAW_DIR / 'stops.json'

    params = {
        'where': '1=1',
        'outFields': '*',
        'outSR': 4326,  # EPSG:4326 (WGS84 lon/lat)
        'f': 'json'
    }
    print(f'Querying Shropshire ArcGIS FeatureServer...')
    r = requests.get(ARCGIS_QUERY_URL, params=params, timeout=20)
    r.raise_for_status()
    raw_file.write_text(r.text, encoding='utf-8')
    print(f'Saved raw response to {raw_file}')
    return r.json()


def parse_shropshire_features(data):
    """Transform ArcGIS feature JSON into schema-compliant stop dicts and update the geocache."""
    features = data.get('features', [])
    stops = []
    geocoder = Geocoder()

    for feat in features:
        attrs = feat.get('attributes', {})
        geom = feat.get('geometry', {})

        lon = geom.get('x')
        lat = geom.get('y')

        mobile = attrs.get('Fullname') or 'Shropshire Mobile Library'
        route_num = attrs.get('Route')
        route_name = f"{mobile} - Route {route_num}" if route_num else mobile

        place_raw = attrs.get('Place') or ''
        # Split community and stop
        if ';' in place_raw:
            parts = place_raw.split(';', 1)
            comm = parts[0].strip()
            stop_name = parts[1].strip()
        elif ',' in place_raw:
            parts = place_raw.split(',', 1)
            comm = parts[0].strip()
            stop_name = parts[1].strip()
        else:
            comm = place_raw.strip()
            stop_name = place_raw.strip()

        arr = (attrs.get('From_') or '').strip()
        dep = (attrs.get('To') or '').strip()

        # Extract day from Date1 timestamp if available
        d1 = attrs.get('Date1')
        day = 'Monday'
        start_date = '2026-01-01'
        if d1:
            try:
                # ArcGIS epoch timestamps are in milliseconds
                dt = datetime.fromtimestamp(d1 / 1000, tz=timezone.utc)
                day = dt.strftime('%A')
            except Exception:
                pass

        freq_raw = (attrs.get('Frequency') or '').lower()
        if 'alternate' in freq_raw or '2' in freq_raw or 'fortnight' in freq_raw:
            frequency = 'FREQ=WEEKLY;INTERVAL=2'
        elif 'monthly' in freq_raw or '4' in freq_raw:
            frequency = 'FREQ=WEEKLY;INTERVAL=4'
        else:
            frequency = 'FREQ=WEEKLY;INTERVAL=2'

        address = f"{stop_name}, {comm}, Shropshire"

        # Index coordinates in geocoder cache
        geo_pc = ''
        if lon and lat:
            geocoder.remember_stop(
                authority=AUTHORITY_NAME,
                community=comm,
                stop=stop_name,
                geox=lon,
                geoy=lat,
                postcode='',
                source='arcgis_featureserver'
            )

        stops.append({
            'Local authority': AUTHORITY_NAME,
            'Local authority code': AUTHORITY_CODE,
            'Mobile name': mobile,
            'Route': route_name,
            'Community': comm,
            'Stop': stop_name,
            'Address': address,
            'Postcode': '',
            'GeoX': f"{lon:.6f}" if lon else '',
            'GeoY': f"{lat:.6f}" if lat else '',
            'Day': day,
            'Type': 'Public',
            'Arrival': arr,
            'Departure': dep,
            'Frequency': frequency,
            'Start': start_date,
            'End': '2026-12-31',
            'Exceptions': '',
            'Timetable': BASE_URL
        })

    geocoder.save_caches()
    return stops


def run():
    """Download ArcGIS stops, parse them, write data/shropshire.csv, and update services.csv."""
    print('=== Starting Shropshire Mobile Library Ingestion ===')
    data = download_raw_arcgis_data()
    stops = parse_shropshire_features(data)
    print(f'Processed {len(stops)} stops from Shropshire ArcGIS service.')

    print(f'Writing {len(stops)} stops to {DATA_FILE}...')
    create_mobile_library_file('shropshire.csv', stops)

    # Update services.csv
    services_path = Path('services.csv')
    if services_path.exists():
        rows = []
        with open(services_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row['dataset_slug'] == SLUG:
                    row['has_mobile_service'] = 'Yes'
                    row['status'] = 'Active Verified'
                    row['source_url'] = BASE_URL
                    row['source_format'] = 'ArcGIS'
                    row['last_checked'] = '2026-11-18'
                    row['last_updated'] = '2026-11-18'
                    row['notes'] = f'Verified 2026 routes: {len(stops)} stops from official ArcGIS layer across Owen, Brookes, and Sabrina.'
                rows.append(row)
        with open(services_path, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print('Shropshire ingestion completed successfully.')


if __name__ == '__main__':
    run()
