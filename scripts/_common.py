"""
Common functions for mobile library data output and schema validation.
Conforms to LibrariesHacked schema-librarydata/mobile-library-stops.json
"""

import csv
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

DATA_OUTPUT = Path(__file__).resolve().parent.parent / 'data'
SCHEMA_PATH = Path(__file__).resolve().parent.parent / 'schemas' / 'mobile-library-stops.json'

SCHEMA_COLUMNS = [
    'local_authority',
    'local_authority_code',
    'mobile_name',
    'route',
    'community',
    'stop',
    'address',
    'postcode',
    'geox',
    'geoy',
    'day',
    'type',
    'arrival',
    'departure',
    'frequency',
    'start',
    'end',
    'exceptions',
    'timetable'
]

TITLE_CASE_MAP = {
    'local_authority': 'Local authority',
    'local_authority_code': 'Local authority code',
    'mobile_name': 'Mobile name',
    'route': 'Route',
    'community': 'Community',
    'stop': 'Stop',
    'address': 'Address',
    'postcode': 'Postcode',
    'geox': 'GeoX',
    'geoy': 'GeoY',
    'day': 'Day',
    'type': 'Type',
    'arrival': 'Arrival',
    'departure': 'Departure',
    'frequency': 'Frequency',
    'start': 'Start',
    'end': 'End',
    'exceptions': 'Exceptions',
    'timetable': 'Timetable'
}


def sanitize_text(value):
    """
    Sanitize text to guarantee single-line CSV data:
    - Strips byte-order marks (\ufeff)
    - Replaces non-breaking spaces (\xa0) with standard spaces
    - Converts newlines (\r\n, \r, \n) into a single space
    - Collapses multiple whitespace/tabs into a single space
    - Strips leading and trailing whitespace
    """
    if value is None:
        return ''
    s = str(value).replace('\ufeff', '').replace('\xa0', ' ')
    s = re.sub(r'[\r\n]+', ' ', s)
    s = re.sub(r'[ \t]+', ' ', s)
    return s.strip()


def sanitize_row(row):
    """
    Sanitize all values in a CSV row (dict or sequence of fields) to ensure
    no field contains embedded newlines or irregular whitespace.
    """
    if isinstance(row, dict):
        return {k: sanitize_text(v) for k, v in row.items()}
    return [sanitize_text(cell) for cell in row]


def create_mobile_library_file(filename, stops):
    """
    Writes stops into a standard CSV file adhering to mobile-library-stops.json.
    Stops can be either a list of dicts (keyed by column name) or list of tuples/lists
    matching SCHEMA_COLUMNS order.
    """
    output_path = DATA_OUTPUT / filename
    DATA_OUTPUT.mkdir(parents=True, exist_ok=True)

    normalized_stops = []
    for item in stops:
        if isinstance(item, dict):
            row = []
            for col in SCHEMA_COLUMNS:
                alt = TITLE_CASE_MAP.get(col)
                val = item.get(col, item.get(alt, ''))
                row.append(val)
        else:
            row = list(item)
        row = sanitize_row(row)
        row = sanitize_row(row)
        for col_idx in (8, 9):
            val = str(row[col_idx]).strip()
            if val:
                try:
                    row[col_idx] = f"{float(val):.5f}"
                except ValueError:
                    pass
        normalized_stops.append(row)

    # Sort by Mobile name (index 2), Route (index 3), and Arrival time (index 12)
    def sort_key(row):
        mobile = str(row[2])
        route = str(row[3])
        time_str = str(row[12]).strip()
        # Normalise H:MM or HH:MM
        if '.' in time_str:
            parts = time_str.split('.')
            time_str = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        elif ':' in time_str:
            parts = time_str.split(':')
            time_str = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        else:
            time_str = '00:00'
        return (mobile, route, time_str)

    normalized_stops = sorted(normalized_stops, key=sort_key)

    with open(output_path, 'w', encoding='utf-8', newline='') as out_csv:
        writer = csv.writer(out_csv, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(SCHEMA_COLUMNS)
        for row in normalized_stops:
            writer.writerow(row)

    print(f"Written {len(normalized_stops)} stops to {output_path}")


# ---------------------------------------------------------------------------
# Shared helpers for "finishing" a dataset: geocoding, validation, registries.
# Each authority script only has to fetch + parse; these cover the rest.
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
GEOCACHE_PATH = ROOT / 'geocache' / 'stops_reference.json'
MANUAL_PINS_PATH = ROOT / 'geocache' / 'manual_pins.json'
BBOX_PATH = ROOT / 'geocache' / 'authority_bboxes.json'
SERVICES_PATH = ROOT / 'services.csv'
VEHICLES_PATH = ROOT / 'history' / 'historical_mobile_vehicles.csv'
HISTORY_STOPS_PATH = ROOT / 'history' / 'historical_mobile_stops.csv'
HTTP_HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; LibrariesHacked-MobileLibraries/1.0)'}


def load_authority_bboxes():
    """Load authority bounding boxes from geocache/authority_bboxes.json."""
    if BBOX_PATH.exists():
        try:
            return json.loads(BBOX_PATH.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


def is_in_bbox(lat, lon, bbox):
    """Check if a coordinate (lat, lon) is within a bounding box.

    bbox can be a dict {'min_lat', 'max_lat', 'min_lon', 'max_lon'} or a 4-tuple.
    """
    if lat is None or lon is None or not bbox:
        return True
    try:
        lat, lon = float(lat), float(lon)
    except (ValueError, TypeError):
        return False
    if isinstance(bbox, dict):
        return (bbox.get('min_lat', -90) <= lat <= bbox.get('max_lat', 90) and
                bbox.get('min_lon', -180) <= lon <= bbox.get('max_lon', 180))
    elif isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        min_lat, max_lat, min_lon, max_lon = bbox
        return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon
    return True


def http_get(url, timeout=25, retries=3):
    """Fetch a URL as bytes, retrying on transient network errors."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HTTP_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.5)


def get_html(url, timeout=25, retries=3):
    """Fetch URL and return text content decoded as UTF-8."""
    return http_get(url, timeout=timeout, retries=retries).decode('utf-8', errors='replace')


def http_post_json(url, payload, timeout=25, retries=3):
    """POST JSON payload to url and return parsed JSON response."""
    body = json.dumps(payload).encode('utf-8')
    headers = {**HTTP_HEADERS, 'Content-Type': 'application/json'}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.5)


def save_raw(raw_dir, filename, url):
    """Download `url` into raw_dir/filename unless already there; return the text.

    Keeping the untouched source means a dataset can be rebuilt offline.
    """
    path = Path(raw_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(http_get(url))
    return path.read_text(encoding='utf-8', errors='replace')


def clean_time_24h(t_str: str, default: str = "") -> str:
    """Normalise arbitrary time strings (e.g. '10.30am', '2pm', '14.15', 'midday', 'noon') to 24-hour HH:MM."""
    if not t_str:
        return default
    s = sanitize_text(t_str).lower()
    if 'midday' in s or 'noon' in s:
        return '12:00'
    m = re.search(r'(\d{1,2})[:.](\d{2})\s*([ap]m)?', s)
    if m:
        h = int(m.group(1))
        m_str = m.group(2)
        ampm = m.group(3)
        if ampm == 'pm' and h < 12:
            h += 12
        elif ampm == 'am' and h == 12:
            h = 0
        elif not ampm and 1 <= h <= 5:  # common UK timetable afternoon convention
            h += 12
        return f"{h:02d}:{m_str}"
    m_hr = re.search(r'(\d{1,2})\s*([ap]m)', s)
    if m_hr:
        h = int(m_hr.group(1))
        ampm = m_hr.group(2)
        if ampm == 'pm' and h < 12:
            h += 12
        elif ampm == 'am' and h == 12:
            h = 0
        return f"{h:02d}:00"
    return default


# Backward-compatibility alias
clean_time = clean_time_24h


def parse_time_range(raw: str) -> tuple:
    """Parse time range string (e.g. '10:00 - 11:30', '10.15am-12.00pm', '1015-1045') into ('HH:MM', 'HH:MM')."""
    if not raw:
        return ("", "")
    cleaned = sanitize_text(raw).replace('–', '-').replace('—', '-')
    parts = cleaned.split('-')
    if len(parts) >= 2:
        t1 = clean_time_24h(parts[0])
        t2 = clean_time_24h(parts[1])
        return (t1, t2)
    times = re.findall(r'(\d{2})(\d{2})', cleaned)
    if len(times) >= 2:
        return (f"{int(times[0][0]):02d}:{times[0][1]}", f"{int(times[1][0]):02d}:{times[1][1]}")
    return ("", "")


def normalise_postcode(pc: str) -> str:
    """Standardise UK postcode format: uppercase with single space, e.g. 'SW1A 1AA'."""
    if not pc:
        return ""
    clean = re.sub(r'[^A-Za-z0-9]', '', str(pc)).upper()
    if len(clean) >= 5:
        return f"{clean[:-3]} {clean[-3:]}"
    return clean


def batch_lookup_postcodes(postcodes_list: list) -> dict:
    """Look up a list of UK postcodes in batches of 100 via api.postcodes.io.

    Returns a dict mapping normalised and raw postcodes to (lat, lon).
    """
    results = {}
    clean_pcs = list({p.replace(" ", "").upper() for p in postcodes_list if p})
    if not clean_pcs:
        return results

    url = "https://api.postcodes.io/postcodes"
    for i in range(0, len(clean_pcs), 100):
        chunk = clean_pcs[i:i + 100]
        try:
            data = http_post_json(url, {"postcodes": chunk})
            for item in data.get("result", []):
                query = item.get("query")
                result = item.get("result")
                if result:
                    coords = (round(result["latitude"], 5), round(result["longitude"], 5))
                    results[query] = coords
                    results[result.get("postcode", "")] = coords
                    results[result.get("postcode", "").replace(" ", "").upper()] = coords
        except Exception:
            pass
    return results


# Backward-compatibility alias
bulk_lookup_postcodes = batch_lookup_postcodes


def batch_reverse_geocode_postcodes(coords_list: list) -> dict:
    """Reverse geocode a list of (lat, lon) coordinates in batches of 100 via api.postcodes.io.

    Returns a dict mapping (round(lat, 5), round(lon, 5)) to postcode string.
    """
    results = {}
    clean_coords = list({(round(lat, 5), round(lon, 5)) for lat, lon in coords_list if lat and lon})
    if not clean_coords:
        return results

    url = "https://api.postcodes.io/postcodes"
    for i in range(0, len(clean_coords), 100):
        chunk = clean_coords[i:i + 100]
        payload = {
            "geolocations": [{"latitude": lat, "longitude": lon, "radius": 1000, "limit": 1} for lat, lon in chunk]
        }
        try:
            data = http_post_json(url, payload)
            for item in data.get("result", []):
                query = item.get("query", {})
                qlat = round(float(query.get("latitude", 0)), 5)
                qlon = round(float(query.get("longitude", 0)), 5)
                sub_res = item.get("result")
                if sub_res and len(sub_res) > 0:
                    results[(qlat, qlon)] = sub_res[0].get("postcode", "")
        except Exception:
            pass
    return results


def to_24h(text, pm_from=1, pm_to=5):
    """Normalise '9.30', '9:30am' or '1.40' to 'HH:MM'. Delegates to clean_time_24h."""
    return clean_time_24h(text)


def load_geocache():
    """Load the shared place -> (lat, lng) cache, overlaying manually verified pins."""
    cache = {}
    if GEOCACHE_PATH.exists():
        try:
            cache = json.loads(GEOCACHE_PATH.read_text(encoding='utf-8'))
        except Exception:
            cache = {}
    if MANUAL_PINS_PATH.exists():
        try:
            manual = json.loads(MANUAL_PINS_PATH.read_text(encoding='utf-8'))
            for k, entry in manual.items():
                if isinstance(entry, dict) and 'geoy' in entry and 'geox' in entry:
                    lat, lng = round(float(entry['geoy']), 5), round(float(entry['geox']), 5)
                    cache[k] = [lat, lng]
                    auth = entry.get('authority', '')
                    comm = entry.get('community', '')
                    stop = entry.get('stop', '')
                    if auth and stop:
                        cache[f"{auth}:{comm}:{stop}".lower()] = [lat, lng]
                        cache[f"{auth}:{stop}".lower()] = [lat, lng]
        except Exception:
            pass
    return cache


def save_geocache(cache):
    """Persist the shared geocache."""
    GEOCACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GEOCACHE_PATH.write_text(json.dumps(cache, indent=2), encoding='utf-8')


def geocode_place(authority, community, stop, cache, session, bbox, county, default,
                  renames=None):
    """Resolve a community name to (lat, lng) using the Postcodes.io places API.

    Lookup order: shared cache (authority:community:stop or manual pins) -> this run's cache
    -> Postcodes.io (enforcing candidate is strictly inside `bbox`) -> `default` centroid.
    `renames` maps awkward timetable spellings to searchable place names.
    """
    full_key = f'{authority}:{community}:{stop}'.lower()
    if full_key in cache:
        res = tuple(cache[full_key])
        if is_in_bbox(res[0], res[1], bbox):
            return res

    short_key = f'{authority}:{stop}'.lower()
    if short_key in cache:
        res = tuple(cache[short_key])
        if is_in_bbox(res[0], res[1], bbox):
            return res

    norm_full = re.sub(r'[^a-z0-9]', '', f'{authority}{community}{stop}'.lower())
    for k, v in cache.items():
        if re.sub(r'[^a-z0-9]', '', k) == norm_full:
            res = tuple(v) if isinstance(v, (list, tuple)) else (v.get('geoy'), v.get('geox'))
            if is_in_bbox(res[0], res[1], bbox):
                return res

    comm_key = f'{authority}:{community}'.lower()
    if comm_key in session:
        return session[comm_key]

    name = community
    for old, new in (renames or {}).items():
        name = name.replace(old, new)
    url = f'https://api.postcodes.io/places?q={urllib.parse.quote(name)}&limit=10'
    try:
        results = json.loads(http_get(url, timeout=8, retries=1)).get('result') or []
        for place in results:
            lat, lng = float(place['latitude']), float(place['longitude'])
            if is_in_bbox(lat, lng, bbox):
                if place.get('county_unitary') == county or not county:
                    session[comm_key] = (round(lat, 5), round(lng, 5))
                    return session[comm_key]
        for place in results:
            lat, lng = float(place['latitude']), float(place['longitude'])
            if is_in_bbox(lat, lng, bbox):
                session[comm_key] = (round(lat, 5), round(lng, 5))
                return session[comm_key]
    except Exception:
        pass
    if is_in_bbox(default[0], default[1], bbox):
        session[comm_key] = default
        return default
    return ('', '')


def reverse_geocode_postcode(lat, lng, cache):
    """Nearest postcode for a coordinate via Postcodes.io ('' if none). Cached in `cache`."""
    key = f'{round(lat, 4)},{round(lng, 4)}'
    if key not in cache:
        url = f'https://api.postcodes.io/postcodes?lat={lat}&lon={lng}&limit=1&radius=1000'
        try:
            result = json.loads(http_get(url, timeout=5, retries=1)).get('result')
            cache[key] = result[0]['postcode'] if result else ''
        except Exception:
            cache[key] = ''
    return cache[key]


def describe_frequency(rrule: str) -> str:
    """Translates an RFC 5545 RRULE string into plain English."""
    if not rrule:
        return ''
    days_map = {
        'MO': 'Monday', 'TU': 'Tuesday', 'WE': 'Wednesday',
        'TH': 'Thursday', 'FR': 'Friday', 'SA': 'Saturday', 'SU': 'Sunday'
    }
    ord_map = {'1': '1st', '2': '2nd', '3': '3rd', '4': '4th', '5': '5th'}
    if rrule.startswith('FREQ=WEEKLY;INTERVAL='):
        interval = rrule.split('=')[-1]
        if interval == '1':
            return 'Weekly'
        elif interval == '2':
            return 'Every 2 weeks'
        return f'Every {interval} weeks'
    elif rrule.startswith('FREQ=MONTHLY;BYDAY='):
        bydays = rrule.split('=')[-1].split(',')
        parts = []
        for bd in bydays:
            ord_num = bd[:-2]
            day_code = bd[-2:]
            parts.append(f"{ord_map.get(ord_num, ord_num)} {days_map.get(day_code, day_code)}")
        return f"Monthly ({', '.join(parts)})"
    return rrule


def validate_dataset(csv_path):
    """Validate a stops CSV against the Frictionless schema; prints and returns validity."""
    from frictionless import Resource, Schema
    schema = Schema(str(SCHEMA_PATH))
    schema.foreign_keys = []
    csv_path = Path(csv_path).resolve()
    # Frictionless rejects absolute paths, so give it a basepath + file name.
    report = Resource(csv_path.name, basepath=str(csv_path.parent), schema=schema).validate()
    messages = [e.message for task in report.tasks for e in task.errors]
    messages += [m for m in report.flatten(['message'])]
    print(f'Validation: valid={report.valid}, errors={len(messages)}')
    for message in messages[:5]:
        print('  ', message)
    return report.valid

def _update_csv(path, key_fn, rows_fn):
    """Read a CSV, let `rows_fn(rows)` mutate it, and write it back with the same header."""
    with open(path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    rows_fn(rows)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def register_vehicles(authority, slug, vehicles, status='Active'):
    """Add vehicles ({name: note}) to history/historical_mobile_vehicles.csv if new."""
    def add(rows):
        known = {(r['Local authority'], r['Mobile name']) for r in rows}
        for name, note in vehicles.items():
            if (authority, name) not in known:
                rows.append({'Local authority': authority, 'Mobile name': name,
                             'Dataset slug': slug, 'Status': status, 'Notes': note})
    _update_csv(VEHICLES_PATH, None, add)


def update_service(code, **fields):
    """Update the services.csv row for a local authority code.

    Pass any column names (status, source_url, notes, ...); last_checked and
    last_updated are set to today automatically.
    """
    today = datetime.now().strftime('%Y-%m-%d')

    def apply(rows):
        for row in rows:
            if row['local_authority_code'] == code:
                row.update(fields)
                row['last_checked'] = row['last_updated'] = today
                return
        raise KeyError(f'{code} not found in services.csv')
    _update_csv(SERVICES_PATH, None, apply)


def format_address(stop, community, area):
    """'Stop, Community, Area' without repeating the name when stop == community."""
    parts = [stop] if stop.lower() == community.lower() else [stop, community]
    return ', '.join(parts + [area])


def archive_stops(rows):
    """Append closed/suspended stops to history/historical_mobile_stops.csv.

    `rows` use the same keys as the history file header; a row is skipped if the
    same authority/community/stop/arrival is already archived. Returns count added.
    """
    added = []

    def add(existing):
        seen = {(r['Local authority'], r['Community'], r['Stop'], r['Arrival']) for r in existing}
        for row in rows:
            key = (row['Local authority'], row['Community'], row['Stop'], row.get('Arrival', ''))
            if key not in seen:
                existing.append(row)
                seen.add(key)
                added.append(row)
    _update_csv(HISTORY_STOPS_PATH, None, add)
    return len(added)
