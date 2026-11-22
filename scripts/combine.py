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

csv.field_size_limit(10_000_000)

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
ROOT_DIR = Path(__file__).resolve().parent.parent
SERVICES_CSV = ROOT_DIR / 'services.csv'
SCHEMA_PATH = ROOT_DIR / 'schemas' / 'mobile-library-stops.json'
OUTPUT_CSV = DATA_DIR / 'uk_mobile_library_stops.csv'
OUTPUT_GEOJSON = DATA_DIR / 'uk_mobile_library_stops.geojson'
OUTPUT_ACCURACY_CSV = DATA_DIR / 'uk_mobile_library_stops_accuracy.csv'
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

    # 3. Validate combined CSV against Frictionless Schema
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


if __name__ == '__main__':
    combine_datasets()
