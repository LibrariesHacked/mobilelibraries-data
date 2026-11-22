"""
Dedicated Lancashire Mobile Library Extractor.
Extracts all 498 official pre-geocoded mobile library stops from Lancashire County
Council's live ArcGIS FeatureServer in WGS84 coordinates, maps them to
schema-librarydata/mobile-library-stops.json, and writes data/lancashire.csv.
"""

import json
import urllib.request
from datetime import datetime
from pathlib import Path

from _common import create_mobile_library_file
from geocoder import Geocoder

ARCGIS_URL = (
    "https://services-eu1.arcgis.com/9MmxkLJT84uEwsJx/arcgis/rest/services/"
    "Mobile_Library_Timetables/FeatureServer/1/query?"
    "where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=json"
)
ARCGIS_ROUTES_URL = (
    "https://services-eu1.arcgis.com/9MmxkLJT84uEwsJx/arcgis/rest/services/"
    "MobileLibraryRoutePath/FeatureServer/1/query?"
    "where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=json"
)
RAW_DIR = Path(__file__).resolve().parent.parent / 'raw' / 'lancashire'
OFFICIAL_ROUTES_DIR = Path(__file__).resolve().parent.parent / 'data' / 'routes' / 'official'
LOCAL_AUTHORITY = 'Lancashire'
LOCAL_AUTHORITY_CODE = 'E10000017'
TIMETABLE_URL = 'https://www.lancashire.gov.uk/libraries/mobile-library/'
DASHBOARD_URL = 'https://lancashirecounty.maps.arcgis.com/apps/dashboards/4da172b047eb4300bd30fc77d974779e'


def fetch_arcgis_data():
    """Fetch live features from Lancashire ArcGIS FeatureServer, saving a dated raw copy for offline reproducibility."""
    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = RAW_DIR / today
    out_file = out_dir / 'arcgis_features.json'
    if out_file.exists():
        return json.loads(out_file.read_text(encoding='utf-8'))

    try:
        print(f"Fetching live stops from Lancashire ArcGIS FeatureServer...")
        req = urllib.request.Request(ARCGIS_URL, headers={"User-Agent": "MobileLibrariesBot/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode('utf-8')
            data = json.loads(content)
            if data.get('features'):
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file.write_text(content, encoding='utf-8')
                return data
    except Exception as e:
        print(f"Warning: Failed to fetch live ArcGIS data ({e}), falling back to cached raw file...")

    # Fallback to most recent cached raw snapshot
    cached_files = sorted(RAW_DIR.glob('*/arcgis_features.json'), reverse=True)
    if cached_files:
        print(f"Loading cached snapshot from {cached_files[0]}")
        return json.loads(cached_files[0].read_text(encoding='utf-8'))

    raise FileNotFoundError("No Lancashire ArcGIS data available (network failed and no cache found).")


def fetch_official_routes():
    """Fetch official Lancashire route paths layer and save as standard GeoJSON in data/routes/official/."""
    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = RAW_DIR / today
    raw_file = out_dir / 'official_routes.json'
    OFFICIAL_ROUTES_DIR.mkdir(parents=True, exist_ok=True)
    out_geojson = OFFICIAL_ROUTES_DIR / 'lancashire_official_routes.geojson'

    try:
        print("Fetching official route paths from Lancashire ArcGIS FeatureServer...")
        req = urllib.request.Request(ARCGIS_ROUTES_URL, headers={"User-Agent": "MobileLibrariesBot/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode('utf-8')
            out_dir.mkdir(parents=True, exist_ok=True)
            raw_file.write_text(content, encoding='utf-8')
            data = json.loads(content)
    except Exception as e:
        print(f"Warning: Failed to fetch official routes ({e}), checking cache...")
        if raw_file.exists():
            data = json.loads(raw_file.read_text(encoding='utf-8'))
        else:
            return None

    day_map = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday', 7: 'Sunday'}
    features = []
    for f in data.get('features', []):
        attrs = f.get('attributes', {})
        geom = f.get('geometry', {})
        paths = geom.get('paths', [])
        if not paths:
            continue

        obj_id = attrs.get('OBJECTID')
        mob = attrs.get('Mobile', '')
        base = attrs.get('BaseLibrary', '')
        route_num = attrs.get('Route', 1)
        day = attrs.get('WeekDay') or ''

        # Map day number or text format
        if not day and attrs.get('DayOfWeekTXT'):
            txt = str(attrs.get('DayOfWeekTXT')).strip()
            if txt.isdigit():
                day = day_map.get(int(txt), '')
            elif '-' in txt:
                day = txt.split('-')[-1].strip()
            else:
                day = txt

        # Handle unlabelled Route 31 feature in official layer
        if not mob and obj_id == 74:
            mob = 'ML3'
            base = 'Garstang'
            route_num = 31
            day = 'Wednesday'

        mob_name = f"{mob} ({base})" if base else mob
        route_name = f"Route {route_num} - {day}" if day else f"Route {route_num}"

        # Standardise to GeoJSON LineString (or MultiLineString)
        if len(paths) == 1:
            geo = {"type": "LineString", "coordinates": paths[0]}
        else:
            geo = {"type": "MultiLineString", "coordinates": paths}

        features.append({
            "type": "Feature",
            "geometry": geo,
            "properties": {
                "mobile": mob_name,
                "route": route_name,
                "district": attrs.get('District', ''),
                "base_library": base,
                "length_m": attrs.get('Shape__Length', 0),
                "source": "official",
                "authority": "Lancashire",
                "authority_code": LOCAL_AUTHORITY_CODE
            }
        })

    geojson_doc = {
        "type": "FeatureCollection",
        "features": features
    }
    out_geojson.write_text(json.dumps(geojson_doc, indent=2), encoding='utf-8')
    print(f"Saved {len(features)} official route polylines to {out_geojson.name}")
    return geojson_doc


def format_time_num(val):
    """Format an integer or string HHMM time (e.g. 930, 1415) as HH:MM, defaulting to '09:00' if falsy."""
    if not val:
        return '09:00'
    val_str = str(val).zfill(4)
    hours = val_str[:2]
    minutes = val_str[2:]
    return f"{int(hours):02d}:{int(minutes):02d}"


def run():
    """Load live or cached Lancashire ArcGIS JSON features, map them to schema rows, update the geocache, and write data/lancashire.csv."""
    geocoder = Geocoder()
    data = fetch_arcgis_data()
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
    fetch_official_routes()


if __name__ == '__main__':
    run()
