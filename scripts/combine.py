"""
Aggregates all individual local authority mobile library stop datasets
into a single nationwide dataset:
- data/uk_mobile_library_stops.csv
- data/uk_mobile_library_stops.geojson
"""

import csv
import json
import re
import sys
from pathlib import Path

# Add scripts directory to path to import _common
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
from _common import sanitize_row

csv.field_size_limit(10_000_000)

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
ROOT_DIR = Path(__file__).resolve().parent.parent
SERVICES_CSV = ROOT_DIR / 'services.csv'
SCHEMA_PATH = ROOT_DIR / 'schemas' / 'mobile-library-stops.json'
OUTPUT_CSV = DATA_DIR / 'uk_mobile_library_stops.csv'
OUTPUT_GEOJSON = DATA_DIR / 'uk_mobile_library_stops.geojson'
OUTPUT_ACCURACY_CSV = DATA_DIR / 'uk_mobile_library_stops_accuracy.csv'
SUMMARY_JSON = DATA_DIR / 'summary.json'
ROUTES_CSV = DATA_DIR / 'uk_mobile_library_routes.csv'
ROUTES_GEOJSON = DATA_DIR / 'uk_mobile_library_routes.geojson'
REF_SERVICES_CSV = DATA_DIR / 'library-services.csv'
MANUAL_PINS_FILE = ROOT_DIR / 'geocache' / 'manual_pins.json'


def normalise_key(text):
    """Lowercase text and strip non-alphanumeric characters."""
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def load_manual_pins():
    """Load manually verified pins if present."""
    if MANUAL_PINS_FILE.exists():
        try:
            return json.loads(MANUAL_PINS_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


def determine_accuracy(row, manual_pins):
    """Classify stop into accuracy tier, source, estimated error radius, and verified flag."""
    auth = row.get("Local authority", "")
    comm = row.get("Community", "")
    stop = row.get("Stop", "")
    pc = (row.get("Postcode") or "").strip().upper()

    auth_k = normalise_key(auth)
    comm_k = normalise_key(comm)
    stop_k = normalise_key(stop)
    full_k = f"{auth_k}::{comm_k}::{stop_k}"
    short_k = f"{auth_k}::{stop_k}"

    if full_k in manual_pins or short_k in manual_pins:
        return "exact", "manual_verified", 5, True

    gis_authorities = {"shropshire", "lancashire", "essex", "norfolk", "bath_and_north_east_somerset"}
    auth_slug = re.sub(r"[^a-z0-9]+", "_", auth.lower()).strip("_")
    if auth_slug in gis_authorities:
        return "exact", "council_gis", 10, False

    landmark_keywords = ["hall", "school", "pub", "inn", "church", "centre", "center", "car park", "surgery"]
    has_landmark = any(kw in stop.lower() or kw in (row.get("Address") or "").lower() for kw in landmark_keywords)

    if pc:
        if has_landmark:
            return "landmark", "named_facility", 25, False
        return "postcode", "postcode_centroid", 100, False

    if has_landmark:
        return "landmark", "community_facility", 50, False

    return "community", "settlement_centroid", 1000, False


def sync_library_services_reference():
    """Generates data/library-services.csv lookup from services.csv to satisfy schema foreignKeys."""
    if not SERVICES_CSV.exists():
        return
    rows = []
    with open(SERVICES_CSV, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            code = r.get('local_authority_code')
            name = r.get('official_name') or r.get('local_authority')
            if code:
                rows.append({'Local authority code': code, 'Local authority': name})
    with open(REF_SERVICES_CSV, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Local authority code', 'Local authority'])
        writer.writeheader()
        writer.writerows(rows)


def combine_datasets():
    """Combines all authority CSV files in data/ into unified CSV and GeoJSON datasets."""
    sync_library_services_reference()

    csv_files = sorted([
        f for f in DATA_DIR.glob('*.csv')
        if not f.name.startswith('uk_')
        and f.name != 'library-services.csv'
        and not f.stem.endswith('_routes')
        and 'review_queue' not in f.name
    ])

    print(f"Combining {len(csv_files)} local authority datasets...")

    manual_pins = load_manual_pins()
    all_rows = []
    accuracy_rows = []
    fieldnames = None
    geocoded_count = 0
    non_geocoded_count = 0
    features = []

    for file_path in csv_files:
        with open(file_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if fieldnames is None:
                fieldnames = reader.fieldnames
            elif reader.fieldnames != fieldnames:
                print(f"Warning: Header mismatch in {file_path.name}")

            for row in reader:
                row = sanitize_row(row)
                all_rows.append(row)

                tier, source, radius_m, verified = determine_accuracy(row, manual_pins)
                accuracy_rows.append({
                    'Local authority': row.get('Local authority', ''),
                    'Local authority code': row.get('Local authority code', ''),
                    'Mobile name': row.get('Mobile name', ''),
                    'Route': row.get('Route', ''),
                    'Community': row.get('Community', ''),
                    'Stop': row.get('Stop', ''),
                    'Address': row.get('Address', ''),
                    'Postcode': row.get('Postcode', ''),
                    'GeoX': row.get('GeoX', ''),
                    'GeoY': row.get('GeoY', ''),
                    'Accuracy tier': tier,
                    'Geocoding source': source,
                    'Estimated radius (m)': radius_m,
                    'Verified': verified
                })

                # Build GeoJSON feature if coordinates are valid
                geox_str = (row.get('GeoX') or '').strip()
                geoy_str = (row.get('GeoY') or '').strip()

                try:
                    if geox_str and geoy_str:
                        lon = round(float(geox_str), 5)
                        lat = round(float(geoy_str), 5)
                        row['GeoX'] = f"{lon:.5f}"
                        row['GeoY'] = f"{lat:.5f}"
                        # Basic UK bounds check (-9.0 to 2.5 lon, 49.0 to 61.5 lat)
                        if -9.0 <= lon <= 2.5 and 49.0 <= lat <= 61.5:
                            geocoded_count += 1
                            feature_props = {
                                k: v for k, v in row.items()
                                if k not in ('GeoX', 'GeoY')
                            }
                            feature_props['accuracy_tier'] = tier
                            feature_props['geocoding_source'] = source
                            feature_props['estimated_radius_m'] = radius_m
                            feature_props['verified'] = verified

                            feature = {
                                "type": "Feature",
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [lon, lat]
                                },
                                "properties": feature_props
                            }
                            features.append(feature)
                        else:
                            non_geocoded_count += 1
                    else:
                        non_geocoded_count += 1
                except ValueError:
                    non_geocoded_count += 1

    # 1. Write unified CSV
    with open(OUTPUT_CSV, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Saved {len(all_rows)} stops to {OUTPUT_CSV.name}")

    # 2. Write unified GeoJSON
    geojson_data = {
        "type": "FeatureCollection",
        "name": "uk_mobile_library_stops",
        "features": features
    }

    with open(OUTPUT_GEOJSON, mode='w', encoding='utf-8') as f:
        json.dump(geojson_data, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(features)} spatial features to {OUTPUT_GEOJSON.name}")
    print(f"Geocoded stops: {geocoded_count} | Ungeocoded stops: {non_geocoded_count}")

    # 3. Write companion accuracy dataset
    accuracy_fieldnames = [
        'Local authority', 'Local authority code', 'Mobile name', 'Route',
        'Community', 'Stop', 'Address', 'Postcode', 'GeoX', 'GeoY',
        'Accuracy tier', 'Geocoding source', 'Estimated radius (m)', 'Verified'
    ]
    with open(OUTPUT_ACCURACY_CSV, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=accuracy_fieldnames)
        writer.writeheader()
        writer.writerows(accuracy_rows)

    print(f"Saved {len(accuracy_rows)} accuracy records to {OUTPUT_ACCURACY_CSV.name}")

    # 4. Combine nationwide route datasets if routes exist
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from routing import combine_routes
        combine_routes()
    except Exception as e:
        print(f"Notice: Route combination skipped: {e}")

    # 5. Generate comprehensive summary JSON
    generate_summary(all_rows, accuracy_rows)

    # 6. Validate combined CSV against Frictionless Schema
    try:
        from frictionless import Resource, Schema
        schema = Schema(str(SCHEMA_PATH))
        schema.foreign_keys = []
        res = Resource(str(OUTPUT_CSV.name), basepath=str(DATA_DIR), schema=schema)
        rep = res.validate()
        if rep.valid:
            print("Unified dataset passed Frictionless Table Schema validation! (valid=True)")
        else:
            print(f"Validation warnings/errors on unified dataset: {len(rep.tasks[0].errors)}")
            for err in rep.flatten(['rowNumber', 'fieldName', 'message'])[:5]:
                print('  ', err)
    except ImportError:
        print("Frictionless not installed; skipped schema validation.")


def generate_summary(all_rows, accuracy_rows):
    """Calculates nationwide service metrics and saves data/summary.json."""
    from collections import Counter, defaultdict
    from datetime import datetime, timezone

    # 1. Authority mappings
    services_map = {}
    if SERVICES_CSV.exists():
        with open(SERVICES_CSV, mode='r', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r.get('dataset_slug'):
                    services_map[r['dataset_slug']] = r
                    services_map[r['local_authority']] = r

    # 2. Stops and accuracy metrics
    authorities = set()
    vehicles = set()
    routes = set()
    auth_stops = defaultdict(list)
    for r in all_rows:
        auth = r.get('Local authority', '')
        mob = r.get('Mobile name', '')
        rt = r.get('Route', '')
        authorities.add(auth)
        vehicles.add((auth, mob))
        routes.add((auth, mob, rt))
        auth_stops[auth].append(r)

    total_acc = Counter()
    auth_acc = defaultdict(Counter)
    for r in accuracy_rows:
        auth = r.get('Local authority', '')
        tier = r.get('Accuracy tier', '')
        total_acc[tier] += 1
        auth_acc[auth][tier] += 1

    total_stops = len(all_rows)

    # 3. Route & travel metrics
    auth_routes = defaultdict(lambda: {'trips': 0, 'dist': 0.0, 'dur': 0.0})
    total_trips = 0
    total_dist_m = 0.0
    total_dur_s = 0.0

    if ROUTES_CSV.exists():
        with open(ROUTES_CSV, mode='r', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                auth = r.get('local_authority', '')
                d = float(r.get('distance', 0) or 0)
                t = float(r.get('duration', 0) or 0)
                total_trips += 1
                total_dist_m += d
                total_dur_s += t
                auth_routes[auth]['trips'] += 1
                auth_routes[auth]['dist'] += d
                auth_routes[auth]['dur'] += t

    total_dist_km = round(total_dist_m / 1000.0, 1)
    total_dist_mi = round(total_dist_km * 0.621371, 1)
    total_dur_hrs = round(total_dur_s / 3600.0, 1)
    avg_leg_dist_km = round((total_dist_km / total_trips), 2) if total_trips else 0.0
    avg_leg_dist_mi = round((avg_leg_dist_km * 0.621371), 2) if total_trips else 0.0
    avg_leg_dur_min = round((total_dur_s / total_trips) / 60.0, 1) if total_trips else 0.0

    exact_c = total_acc.get('exact', 0)
    landmark_c = total_acc.get('landmark', 0)
    postcode_c = total_acc.get('postcode', 0)
    community_c = total_acc.get('community', 0)
    high_conf_c = exact_c + landmark_c + postcode_c

    # 4. Per-authority list
    authorities_list = []
    for auth in sorted(authorities):
        s_rows = auth_stops[auth]
        auth_code = s_rows[0].get('Local authority code', '') if s_rows else ''
        auth_slug = ''
        if auth in services_map:
            auth_slug = services_map[auth].get('dataset_slug', '')
        elif auth_code:
            for s_info in services_map.values():
                if s_info.get('local_authority_code') == auth_code:
                    auth_slug = s_info.get('dataset_slug', '')
                    break

        auth_v = {r.get('Mobile name', '') for r in s_rows}
        auth_r = {(r.get('Mobile name', ''), r.get('Route', '')) for r in s_rows}
        r_info = auth_routes[auth]
        a_acc = auth_acc[auth]

        authorities_list.append({
            'local_authority': auth,
            'local_authority_code': auth_code,
            'dataset_slug': auth_slug,
            'vehicles': len(auth_v),
            'routes': len(auth_r),
            'stops': len(s_rows),
            'trips': r_info['trips'],
            'distance_km': round(r_info['dist'] / 1000.0, 1),
            'distance_miles': round((r_info['dist'] / 1000.0) * 0.621371, 1),
            'duration_hours': round(r_info['dur'] / 3600.0, 1),
            'accuracy': {
                'exact': a_acc.get('exact', 0),
                'landmark': a_acc.get('landmark', 0),
                'postcode': a_acc.get('postcode', 0),
                'community': a_acc.get('community', 0)
            }
        })

    summary_data = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'national_totals': {
            'authorities_with_mobile_service': len(authorities),
            'active_vehicles': len(vehicles),
            'routes': len(routes),
            'stops': total_stops,
            'trips': total_trips,
            'distance_km': total_dist_km,
            'distance_miles': total_dist_mi,
            'duration_hours': total_dur_hrs,
            'average_trip_distance_km': avg_leg_dist_km,
            'average_trip_distance_miles': avg_leg_dist_mi,
            'average_trip_duration_minutes': avg_leg_dur_min
        },
        'coordinate_accuracy': {
            'exact': {'count': exact_c, 'percentage': round(exact_c / total_stops * 100, 1) if total_stops else 0},
            'landmark': {'count': landmark_c, 'percentage': round(landmark_c / total_stops * 100, 1) if total_stops else 0},
            'postcode': {'count': postcode_c, 'percentage': round(postcode_c / total_stops * 100, 1) if total_stops else 0},
            'community': {'count': community_c, 'percentage': round(community_c / total_stops * 100, 1) if total_stops else 0},
            'high_confidence_total': {'count': high_conf_c, 'percentage': round(high_conf_c / total_stops * 100, 1) if total_stops else 0}
        },
        'authorities': authorities_list
    }

    with open(SUMMARY_JSON, mode='w', encoding='utf-8') as f:
        json.dump(summary_data, f, indent=2)

    print(f"✓ Saved national statistics summary to {SUMMARY_JSON.name}")


if __name__ == '__main__':
    combine_datasets()
