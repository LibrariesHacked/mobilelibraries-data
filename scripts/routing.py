"""
Unified Routing Engine for Mobile Library Datasets.
Uses OpenRouteService (driving-hgv profile) to generate route geometries
(GeoJSON) and road trip segments (CSV).
"""

import argparse
import collections
import csv
import json
import time
from pathlib import Path
import requests

API_KEY = '5b3ce3597851110001cf624843265134879f4af891bea9acf99ebbc7'
DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
ORS_URL = 'https://api.openrouteservice.org/v2/directions/driving-hgv/geojson'


def generate_routes_for_authority(slug, force=False):
    stop_file = DATA_DIR / f"{slug}.csv"
    output_geojson = DATA_DIR / f"{slug}_routes.geojson"
    output_csv = DATA_DIR / f"{slug}_routes.csv"

    if not stop_file.exists():
        print(f"Error: {stop_file} does not exist.")
        return False

    if output_geojson.exists() and output_csv.exists() and not force:
        print(f"Routes already exist for {slug}. Use --force to regenerate.")
        return True

    routes = collections.defaultdict(list)
    with open(stop_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Handle new and legacy schema column names
            mobile = row.get('Mobile name') or row.get('mobile') or 'Mobile'
            route = row.get('Route') or row.get('route') or 'Default'
            routes[(mobile, route)].append(row)

    features = []
    trip_rows = []
    headers = {'Authorization': API_KEY}

    print(f"[{slug}] Processing {len(routes)} route schedules...")

    for (mobile, route), stops in routes.items():
        coords = []
        valid_stops = []
        for s in stops:
            x = s.get('GeoX') or s.get('geox') or ''
            y = s.get('GeoY') or s.get('geoy') or ''
            if x and y:
                try:
                    coords.append([float(x), float(y)])
                    valid_stops.append(s)
                except ValueError:
                    continue

        if len(coords) < 2:
            continue

        try:
            res = requests.post(ORS_URL, json={'coordinates': coords}, headers=headers, timeout=25)
            res_data = res.json()
            if 'error' in res_data:
                print(f"[{slug}] ORS notice for {mobile} {route}: {res_data.get('error')}")
                time.sleep(1.5)
                continue

            feature = res_data['features'][0]
            feature['properties']['mobile'] = mobile
            feature['properties']['route'] = route
            features.append(feature)

            waypoints = feature['properties'].get('way_points', [])
            segments = feature['properties'].get('segments', [])
            geometry_coords = feature['geometry']['coordinates']

            for i in range(len(segments)):
                origin = valid_stops[i]
                destination = valid_stops[i + 1]
                start_idx = waypoints[i]
                end_idx = waypoints[i + 1] + 1
                segment_coords = geometry_coords[start_idx:end_idx]
                wkt_linestring = "LINESTRING (" + ",".join([f"{c[0]} {c[1]}" for c in segment_coords]) + ")"

                trip_rows.append({
                    'WKT': wkt_linestring,
                    'destination_stop': destination.get('Stop') or destination.get('stop') or '',
                    'destination_stop_latitude': destination.get('GeoY') or destination.get('geoy') or '',
                    'destination_stop_longitude': destination.get('GeoX') or destination.get('geox') or '',
                    'distance': segments[i].get('distance', 0),
                    'duration': segments[i].get('duration', 0),
                    'mobile': mobile,
                    'origin_stop': origin.get('Stop') or origin.get('stop') or '',
                    'origin_stop_latitude': origin.get('GeoY') or origin.get('geoy') or '',
                    'origin_stop_longitude': origin.get('GeoX') or origin.get('geox') or '',
                    'route': route
                })

            time.sleep(1.2)
        except Exception as e:
            print(f"[{slug}] Routing failed for {mobile} {route}: {e}")

    with open(output_geojson, 'w', encoding='utf-8') as f:
        json.dump({'type': 'FeatureCollection', 'features': features}, f, indent=2)

    fieldnames = [
        'WKT', 'destination_stop', 'destination_stop_latitude', 'destination_stop_longitude',
        'distance', 'duration', 'mobile', 'origin_stop', 'origin_stop_latitude',
        'origin_stop_longitude', 'route'
    ]
    with open(output_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(trip_rows)

    print(f"[{slug}] Saved {len(features)} route geometries and {len(trip_rows)} trip segments.")
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate routes for mobile library datasets.')
    parser.add_argument('--authority', '-a', help='Dataset slug (e.g. leicestershire, north_somerset)')
    parser.add_argument('--all', action='store_true', help='Generate routes for all datasets in data/')
    parser.add_argument('--force', '-f', action='store_true', help='Force regenerate existing route files')
    args = parser.parse_args()

    if args.authority:
        generate_routes_for_authority(args.authority, force=args.force)
    elif args.all:
        for p in sorted(DATA_DIR.glob('*.csv')):
            if not p.stem.endswith('_routes'):
                generate_routes_for_authority(p.stem, force=args.force)
    else:
        parser.print_help()
