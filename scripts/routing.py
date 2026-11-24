"""Unified Routing Engine for Mobile Library Datasets.

Generates route geometries (GeoJSON) and road trip segments (CSV).
Supports:
1. OpenRouteService (driving-hgv profile) when ORS_API_KEY is configured.
2. OSRM (OpenStreetMap driving network) as an open zero-config routing engine.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import os
import time
from pathlib import Path
from typing import Any

import requests

# Add scripts directory to path to import _common
SCRIPTS_DIR = Path(__file__).resolve().parent
import sys
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
from _common import sanitize_row

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ROUTES_DIR = DATA_DIR / "routes"
OFFICIAL_ROUTES_DIR = ROUTES_DIR / "official"
ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv/geojson"
DEFAULT_OSRM_URL = "http://router.project-osrm.org/route/v1/driving"
OSRM_URL_BASE = os.environ.get("OSRM_URL", DEFAULT_OSRM_URL)


def haversine_distance(coord1: list[float], coord2: list[float]) -> float:
    """Calculate great-circle distance in metres between two [lon, lat] coordinates."""
    lon1, lat1 = coord1
    lon2, lat2 = coord2
    r = 6371000.0  # Earth radius in metres
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def polyline_length(coords: list[list[float]]) -> float:
    """Calculate cumulative length of coordinate list in metres."""
    if len(coords) < 2:
        return 0.0
    return sum(haversine_distance(coords[i], coords[i + 1]) for i in range(len(coords) - 1))


def find_nearest_coord_index(pt: list[float], coords: list[list[float]], start_idx: int = 0) -> int:
    """Find index of coordinate in coords closest to pt, starting search from start_idx."""
    best_idx = start_idx
    best_dist = float("inf")
    for idx in range(start_idx, len(coords)):
        d = haversine_distance(pt, coords[idx])
        if d < best_dist:
            best_dist = d
            best_idx = idx
    return best_idx


def route_ors(coords: list[list[float]], api_key: str) -> dict[str, Any] | None:
    """Route coordinates using OpenRouteService driving-hgv profile."""
    headers = {"Authorization": api_key}
    res = requests.post(ORS_URL, json={"coordinates": coords}, headers=headers, timeout=25)
    res_data = res.json()
    if "error" in res_data:
        print(f"  [ORS Notice] {res_data.get('error')}")
        return None
    return res_data


def route_osrm(coords: list[list[float]], osrm_base: str = OSRM_URL_BASE) -> dict[str, Any] | None:
    """Route coordinates using the OSRM driving engine."""
    coord_str = ";".join(f"{c[0]:.5f},{c[1]:.5f}" for c in coords)
    url = f"{osrm_base}/{coord_str}?overview=full&geometries=geojson&steps=true"
    res = requests.get(url, headers={"User-Agent": "MobileLibrariesRouting/1.0"}, timeout=25)
    if res.status_code != 200:
        return None
    data = res.json()
    if data.get("code") != "Ok":
        return None

    # Normalise OSRM response to ORS-compatible feature structure
    route = data["routes"][0]
    legs = route.get("legs", [])
    geometry_coords = route.get("geometry", {}).get("coordinates", [])

    # Map legs into segments with cumulative step waypoints
    segments = []
    way_points = [0]
    curr_idx = 0

    for leg in legs:
        leg_steps = leg.get("steps", [])
        step_pts = sum(len(st.get("geometry", {}).get("coordinates", [])) for st in leg_steps)
        curr_idx = min(len(geometry_coords) - 1, curr_idx + max(1, step_pts))
        way_points.append(curr_idx)
        segments.append({
            "distance": round(leg.get("distance", 0), 1),
            "duration": round(leg.get("duration", 0), 1),
        })

    feature = {
        "type": "Feature",
        "geometry": route.get("geometry"),
        "properties": {
            "segments": segments,
            "way_points": way_points,
            "summary": {
                "distance": round(route.get("distance", 0), 1),
                "duration": round(route.get("duration", 0), 1),
            },
        },
    }
    return {"features": [feature]}


def load_existing_routes(output_geojson: Path, output_csv: Path) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[tuple[str, str], list[dict[str, str]]]]:
    """Loads existing route features and trip rows indexed by (mobile, route)."""
    existing_features = {}
    existing_trips = collections.defaultdict(list)

    if output_geojson.exists():
        try:
            with open(output_geojson, mode="r", encoding="utf-8") as f:
                data = json.load(f)
                for feat in data.get("features", []):
                    props = feat.get("properties", {})
                    mob = props.get("mobile", "")
                    rt = props.get("route", "")
                    if mob and rt:
                        existing_features[(mob, rt)] = feat
        except Exception:
            pass

    if output_csv.exists():
        try:
            with open(output_csv, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    mob = row.get("mobile", "")
                    rt = row.get("route", "")
                    if mob and rt:
                        existing_trips[(mob, rt)].append(row)
        except Exception:
            pass

    return existing_features, existing_trips


def generate_routes_for_authority(
    slug: str,
    force: bool = False,
    engine: str = "auto",
    osrm_url: str = OSRM_URL_BASE,
    force_engine: bool = False,
) -> bool:
    """Generate road geometries and trip segments for slug with per-route change detection.

    Priority:
    1. Uses official council polylines from data/routes/official/<slug>_official_routes.geojson if available.
    2. Otherwise falls back to OSRM / OpenRouteService routing.
    """
    stop_file = DATA_DIR / f"{slug}.csv"
    ROUTES_DIR.mkdir(parents=True, exist_ok=True)
    output_geojson = ROUTES_DIR / f"{slug}_routes.geojson"
    output_csv = ROUTES_DIR / f"{slug}_routes.csv"

    if not stop_file.exists():
        print(f"Error: {stop_file} does not exist.")
        return False

    api_key = os.environ.get("ORS_API_KEY", "")
    use_ors = (engine == "ors") or (engine == "auto" and bool(api_key))
    engine_name = "OpenRouteService (driving-hgv)" if use_ors else f"OSRM ({osrm_url})"

    # Check for official council route polylines
    official_file = OFFICIAL_ROUTES_DIR / f"{slug}_official_routes.geojson"
    official_map: dict[tuple[str, str], dict[str, Any]] = {}
    if official_file.exists() and not force_engine:
        try:
            with open(official_file, mode="r", encoding="utf-8") as f:
                off_doc = json.load(f)
                for f_feat in off_doc.get("features", []):
                    f_mob = f_feat.get("properties", {}).get("mobile", "")
                    f_rt = f_feat.get("properties", {}).get("route", "")
                    if f_mob and f_rt:
                        official_map[(f_mob, f_rt)] = f_feat
            print(f"[{slug}] Found {len(official_map)} official route polylines in {official_file.name}")
        except Exception as e:
            print(f"Warning: Failed to load {official_file}: {e}")

    routes = collections.defaultdict(list)
    with open(stop_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mobile = row.get("Mobile name") or row.get("mobile") or "Mobile"
            route = row.get("Route") or row.get("route") or "Default"
            routes[(mobile, route)].append(row)

    existing_features, existing_trips = load_existing_routes(output_geojson, output_csv)

    features = []
    trip_rows = []
    updated_routes = 0
    reused_routes = 0

    for (mobile, route) in sorted(routes.keys()):
        stops = routes[(mobile, route)]
        # Chronological sorting by arrival time ensures sequential driving order
        stops.sort(key=lambda s: s.get("arrival") or s.get("Arrival", ""))

        valid_stops = []
        for s in stops:
            x = s.get("GeoX") or s.get("geox") or ""
            y = s.get("GeoY") or s.get("geoy") or ""
            if x and y:
                try:
                    valid_stops.append({
                        "stop": s.get("Stop") or s.get("stop") or "",
                        "x": round(float(x), 5),
                        "y": round(float(y), 5),
                        "raw": s,
                    })
                except ValueError:
                    continue

        if len(valid_stops) < 2:
            continue

        # Priority 1: Use official council route polyline if available
        if (mobile, route) in official_map:
            off_feat = official_map[(mobile, route)]
            off_geom = off_feat.get("geometry", {})
            raw_coords = off_geom.get("coordinates", [])
            # Normalise MultiLineString coordinates
            if off_geom.get("type") == "MultiLineString":
                coords = [pt for sub in raw_coords for pt in sub]
            else:
                coords = raw_coords

            curr_idx = 0
            for i in range(len(valid_stops) - 1):
                st_orig = valid_stops[i]
                st_dest = valid_stops[i + 1]
                p_orig = [st_orig["x"], st_orig["y"]]
                p_dest = [st_dest["x"], st_dest["y"]]

                idx1 = find_nearest_coord_index(p_orig, coords, curr_idx)
                idx2 = find_nearest_coord_index(p_dest, coords, idx1)
                curr_idx = idx2

                if idx2 > idx1:
                    seg_coords = coords[idx1 : idx2 + 1]
                else:
                    seg_coords = [p_orig, p_dest]

                dist = round(polyline_length(seg_coords), 1)
                dur = round(dist / 11.11)  # ~40 km/h average driving speed

                wkt = "LINESTRING (" + ",".join([f"{c[0]} {c[1]}" for c in seg_coords]) + ")"
                trip_rows.append({
                    "WKT": wkt,
                    "destination_stop": st_dest["raw"].get("stop") or st_dest["raw"].get("Stop") or "",
                    "destination_stop_latitude": f"{st_dest['y']:.5f}",
                    "destination_stop_longitude": f"{st_dest['x']:.5f}",
                    "distance": dist,
                    "duration": dur,
                    "mobile": mobile,
                    "origin_stop": st_orig["raw"].get("stop") or st_orig["raw"].get("Stop") or "",
                    "origin_stop_latitude": f"{st_orig['y']:.5f}",
                    "origin_stop_longitude": f"{st_orig['x']:.5f}",
                    "route": route,
                })

            feature = {
                "type": "Feature",
                "geometry": off_geom,
                "properties": {
                    "mobile": mobile,
                    "route": route,
                    "source": "official",
                    "authority": off_feat.get("properties", {}).get("authority", slug.replace("_", " ").title()),
                }
            }
            features.append(feature)
            updated_routes += 1
            continue

        # Check if route coordinates are identical to existing routed segments
        is_unchanged = False
        if not force and (mobile, route) in existing_features and (mobile, route) in existing_trips:
            trips = existing_trips[(mobile, route)]
            if len(trips) == len(valid_stops) - 1:
                coords_match = True
                for i, st in enumerate(valid_stops[:-1]):
                    try:
                        orig_x = round(float(trips[i]["origin_stop_longitude"]), 5)
                        orig_y = round(float(trips[i]["origin_stop_latitude"]), 5)
                        if (orig_x, orig_y) != (st["x"], st["y"]):
                            coords_match = False
                            break
                    except (ValueError, KeyError):
                        coords_match = False
                        break
                if coords_match:
                    try:
                        last_x = round(float(trips[-1]["destination_stop_longitude"]), 5)
                        last_y = round(float(trips[-1]["destination_stop_latitude"]), 5)
                        last_st = valid_stops[-1]
                        if (last_x, last_y) == (last_st["x"], last_st["y"]):
                            is_unchanged = True
                    except (ValueError, KeyError):
                        pass

        if is_unchanged:
            features.append(existing_features[(mobile, route)])
            trip_rows.extend(existing_trips[(mobile, route)])
            reused_routes += 1
            continue

        # Route coordinates have changed (or route is new/forced) -> regenerate route
        coords = [[st["x"], st["y"]] for st in valid_stops]
        try:
            print(f"  [{slug}] Routing '{route}' ({len(coords)} stops) via {engine_name}...")
            if use_ors:
                res_data = route_ors(coords, api_key)
            else:
                res_data = route_osrm(coords, osrm_base=osrm_url)

            if not res_data or "features" not in res_data or not res_data["features"]:
                # If network fails but we had an existing feature, preserve it as fallback
                if (mobile, route) in existing_features:
                    features.append(existing_features[(mobile, route)])
                    trip_rows.extend(existing_trips[(mobile, route)])
                time.sleep(1.0)
                continue

            feature = res_data["features"][0]
            feature["properties"]["mobile"] = mobile
            feature["properties"]["route"] = route
            features.append(feature)

            waypoints = feature["properties"].get("way_points", [])
            segments = feature["properties"].get("segments", [])
            geometry_coords = feature["geometry"]["coordinates"]

            for i in range(len(segments)):
                if i + 1 >= len(valid_stops):
                    break
                origin = valid_stops[i]["raw"]
                destination = valid_stops[i + 1]["raw"]

                # Determine coordinate slice for this segment
                if i < len(waypoints) and i + 1 < len(waypoints):
                    start_idx = waypoints[i]
                    end_idx = min(len(geometry_coords), waypoints[i + 1] + 1)
                    segment_coords = geometry_coords[start_idx:end_idx]
                else:
                    segment_coords = geometry_coords

                if not segment_coords:
                    segment_coords = [
                        [valid_stops[i]["x"], valid_stops[i]["y"]],
                        [valid_stops[i + 1]["x"], valid_stops[i + 1]["y"]]
                    ]

                wkt_linestring = "LINESTRING (" + ",".join([f"{c[0]} {c[1]}" for c in segment_coords]) + ")"

                trip_rows.append({
                    "WKT": wkt_linestring,
                    "destination_stop": destination.get("Stop") or destination.get("stop") or "",
                    "destination_stop_latitude": f"{valid_stops[i + 1]['y']:.5f}",
                    "destination_stop_longitude": f"{valid_stops[i + 1]['x']:.5f}",
                    "distance": segments[i].get("distance", 0),
                    "duration": segments[i].get("duration", 0),
                    "mobile": mobile,
                    "origin_stop": origin.get("Stop") or origin.get("stop") or "",
                    "origin_stop_latitude": f"{valid_stops[i]['y']:.5f}",
                    "origin_stop_longitude": f"{valid_stops[i]['x']:.5f}",
                    "route": route,
                })

            updated_routes += 1
            time.sleep(0.35 if not use_ors else 1.5)
        except Exception as e:
            print(f"[{slug}] Routing failed for {mobile} {route}: {e}")
            if (mobile, route) in existing_features:
                features.append(existing_features[(mobile, route)])
                trip_rows.extend(existing_trips[(mobile, route)])

    if updated_routes == 0 and output_geojson.exists() and output_csv.exists() and not force:
        print(f"[{slug}] Up to date: all {reused_routes} routes unchanged.")
        return True

    with open(output_geojson, mode="w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, indent=2)

    fieldnames = [
        "WKT", "destination_stop", "destination_stop_latitude", "destination_stop_longitude",
        "distance", "duration", "mobile", "origin_stop", "origin_stop_latitude",
        "origin_stop_longitude", "route",
    ]
    with open(output_csv, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows([sanitize_row(t) for t in trip_rows])

    print(f"[{slug}] Saved {len(features)} route geometries ({updated_routes} updated, {reused_routes} unchanged).")
    return True


def combine_routes() -> None:
    """Combines all authority route GeoJSONs and CSVs into nationwide UK datasets:
    - data/uk_mobile_library_routes.geojson
    - data/uk_mobile_library_routes.csv
    """
    slug_to_auth = {}
    services_file = DATA_DIR.parent / "services.csv"
    if services_file.exists():
        with open(services_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                slug = row.get("dataset_slug")
                if slug:
                    slug_to_auth[slug] = {
                        "name": row.get("local_authority", ""),
                        "code": row.get("local_authority_code", ""),
                    }

    geojson_files = sorted(ROUTES_DIR.glob("*_routes.geojson"))
    csv_files = sorted(ROUTES_DIR.glob("*_routes.csv"))

    all_features = []
    for gf in geojson_files:
        if gf.name.startswith("uk_"):
            continue
        slug = gf.name.replace("_routes.geojson", "")
        auth_info = slug_to_auth.get(slug, {"name": slug.replace("_", " ").title(), "code": ""})
        try:
            with open(gf, mode="r", encoding="utf-8") as f:
                data = json.load(f)
                for feat in data.get("features", []):
                    feat_copy = dict(feat)
                    feat_copy["properties"] = dict(feat.get("properties", {}))
                    feat_copy["properties"]["local_authority"] = auth_info["name"]
                    feat_copy["properties"]["local_authority_code"] = auth_info["code"]
                    all_features.append(feat_copy)
        except Exception as e:
            print(f"Warning: Failed to read {gf.name}: {e}")

    out_geojson = DATA_DIR / "uk_mobile_library_routes.geojson"
    with open(out_geojson, mode="w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": all_features}, f, separators=(",", ":"))
    print(f"✓ Combined {len(all_features)} routes into {out_geojson.name}")

    all_trips = []
    fieldnames = [
        "local_authority", "local_authority_code", "mobile", "route",
        "origin_stop", "origin_stop_latitude", "origin_stop_longitude",
        "destination_stop", "destination_stop_latitude", "destination_stop_longitude",
        "distance", "duration", "WKT",
    ]
    for cf in csv_files:
        if cf.name.startswith("uk_"):
            continue
        slug = cf.name.replace("_routes.csv", "")
        auth_info = slug_to_auth.get(slug, {"name": slug.replace("_", " ").title(), "code": ""})
        try:
            with open(cf, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row["local_authority"] = auth_info["name"]
                    row["local_authority_code"] = auth_info["code"]
                    all_trips.append(row)
        except Exception as e:
            print(f"Warning: Failed to read {cf.name}: {e}")

    out_csv = DATA_DIR / "uk_mobile_library_routes.csv"
    with open(out_csv, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows([sanitize_row(t) for t in all_trips])
    print(f"✓ Combined {len(all_trips)} trip legs into {out_csv.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate routes for mobile library datasets.")
    parser.add_argument("--authority", "-a", help="Dataset slug (e.g. shropshire, north_somerset)")
    parser.add_argument("--all", action="store_true", help="Generate routes for all datasets in data/")
    parser.add_argument("--combine", action="store_true", help="Combine existing route files into UK datasets")
    parser.add_argument("--force", "-f", action="store_true", help="Force regenerate existing route files")
    parser.add_argument("--engine", choices=["auto", "ors", "osrm"], default="auto", help="Routing engine")
    parser.add_argument("--osrm-url", default=OSRM_URL_BASE, help=f"Custom OSRM routing endpoint (default: {DEFAULT_OSRM_URL})")
    parser.add_argument("--force-engine", action="store_true", help="Force synthetic engine routing even if official council polylines exist")
    args = parser.parse_args()

    if args.authority:
        generate_routes_for_authority(
            args.authority,
            force=args.force,
            engine=args.engine,
            osrm_url=args.osrm_url,
            force_engine=args.force_engine,
        )
    elif args.combine:
        combine_routes()
    elif args.all:
        for p in sorted(DATA_DIR.glob("*.csv")):
            if (
                p.name.startswith("uk_")
                or p.stem.endswith("_routes")
                or p.name.startswith("library-services")
                or "review_queue" in p.name
            ):
                continue
            generate_routes_for_authority(
                p.stem,
                force=args.force,
                engine=args.engine,
                osrm_url=args.osrm_url,
                force_engine=args.force_engine,
            )
        combine_routes()
    else:
        parser.print_help()
