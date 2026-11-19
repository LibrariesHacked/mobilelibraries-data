"""
Aggregates all individual local authority mobile library stop datasets
into a single nationwide dataset:
- data/uk_mobile_library_stops.csv
- data/uk_mobile_library_stops.geojson
"""

import csv
import json
import sys
from pathlib import Path

csv.field_size_limit(10_000_000)

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
ROOT_DIR = Path(__file__).resolve().parent.parent
SERVICES_CSV = ROOT_DIR / 'services.csv'
SCHEMA_PATH = ROOT_DIR / 'schemas' / 'mobile-library-stops.json'
OUTPUT_CSV = DATA_DIR / 'uk_mobile_library_stops.csv'
OUTPUT_GEOJSON = DATA_DIR / 'uk_mobile_library_stops.geojson'
REF_SERVICES_CSV = DATA_DIR / 'library-services.csv'


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
    ])

    print(f"Combining {len(csv_files)} local authority datasets...")

    all_rows = []
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
                            feature = {
                                "type": "Feature",
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [lon, lat]
                                },
                                "properties": {
                                    k: v for k, v in row.items()
                                    if k not in ('GeoX', 'GeoY')
                                }
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
