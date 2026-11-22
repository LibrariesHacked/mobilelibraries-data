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
import os
import time
from pathlib import Path
from typing import Any

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ROUTES_DIR = DATA_DIR / "routes"
ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv/geojson"
OSRM_URL_BASE = "http://router.project-osrm.org/route/v1/driving"


def route_ors(coords: list[list[float]], api_key: str) -> dict[str, Any] | None:
    """Route coordinates using OpenRouteService driving-hgv profile."""
    headers = {"Authorization": api_key}
    res = requests.post(ORS_URL, json={"coordinates": coords}, headers=headers, timeout=25)
    res_data = res.json()
    if "error" in res_data:
        print(f"  [ORS Notice] {res_data.get('error')}")
        return None
    return res_data


def route_osrm(coords: list[list[float]]) -> dict[str, Any] | None:
    """Route coordinates using the public OSRM driving engine."""
    coord_str = ";".join(f"{c[0]:.5f},{c[1]:.5f}" for c in coords)
    url = f"{OSRM_URL_BASE}/{coord_str}?overview=full&geometries=geojson&steps=true"
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


def generate_routes_for_authority(slug: str, force: bool = False, engine: str = "auto") -> bool:
    """Generate road geometries and trip segments for slug with per-route change detection."""
    stop_file = DATA_DIR / f"{slug}.csv"
    ROUTES_DIR.mkdir(parents=True, exist_ok=True)
    output_geojson = ROUTES_DIR / f"{slug}_routes.geojson"
    output_csv = ROUTES_DIR / f"{slug}_routes.csv"

    if not stop_file.exists():
        print(f"Error: {stop_file} does not exist.")
        return False

    api_key = os.environ.get("ORS_API_KEY", "")
    use_ors = (engine == "ors") or (engine == "auto" and bool(api_key))
    engine_name = "OpenRouteService (driving-hgv)" if use_ors else "OSRM (OpenStreetMap driving)"

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
        stops.sort(key=lambda s: s.get("Arrival", ""))

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
                res_data = route_osrm(coords)

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
        writer.writerows(trip_rows)

    print(f"[{slug}] Saved {len(features)} route geometries ({updated_routes} updated, {reused_routes} unchanged).")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate routes for mobile library datasets.")
    parser.add_argument("--authority", "-a", help="Dataset slug (e.g. shropshire, north_somerset)")
    parser.add_argument("--all", action="store_true", help="Generate routes for all datasets in data/")
    parser.add_argument("--force", "-f", action="store_true", help="Force regenerate existing route files")
    parser.add_argument("--engine", choices=["auto", "ors", "osrm"], default="auto", help="Routing engine")
    args = parser.parse_args()

    if args.authority:
        generate_routes_for_authority(args.authority, force=args.force, engine=args.engine)
    elif args.all:
        for p in sorted(DATA_DIR.glob("*.csv")):
            if (
                p.name.startswith("uk_")
                or p.stem.endswith("_routes")
                or p.name.startswith("library-services")
                or "review_queue" in p.name
            ):
                continue
            generate_routes_for_authority(p.stem, force=args.force, engine=args.engine)
    else:
        parser.print_help()
