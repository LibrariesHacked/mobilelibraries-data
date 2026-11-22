"""Automated Coordinate Upgrader using OpenStreetMap Nominatim.

Finds exact street, building, school, hall, and landmark coordinates for stops
that currently only have coarse community-level centroids.

Usage:
  python scripts/upgrade_coordinates.py --authority leicestershire [--limit 20]
  python scripts/upgrade_coordinates.py --authority nottinghamshire
  python scripts/upgrade_coordinates.py --all --limit 50
  python scripts/upgrade_coordinates.py --dry-run --authority conwy
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
GEOCACHE_DIR = ROOT / "geocache"
MANUAL_PINS_FILE = GEOCACHE_DIR / "manual_pins.json"
STOPS_REF_FILE = GEOCACHE_DIR / "stops_reference.json"
BBOX_FILE = GEOCACHE_DIR / "authority_bboxes.json"

USER_AGENT = "LibrariesHacked-MobileLibraries-Bot/1.0 (info@librarieshacked.org)"


def normalise_key(text: str) -> str:
    """Lowercase text and strip non-alphanumeric characters."""
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in kilometres."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def load_json(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def is_in_bbox(lat: float, lon: float, bbox: dict[str, float] | None) -> bool:
    if not bbox:
        return True
    return (
        bbox.get("min_lat", -90) <= lat <= bbox.get("max_lat", 90)
        and bbox.get("min_lon", -180) <= lon <= bbox.get("max_lon", 180)
    )


def extract_postcode(display_name: str) -> str:
    """Extract standard UK postcode from Nominatim display_name if present."""
    match = re.search(r"\b([A-Z]{1,2}[0-9][0-9A-Z]?\s*[0-9][A-Z]{2})\b", display_name, re.IGNORECASE)
    if match:
        raw = match.group(1).upper()
        # Normalise spacing
        parts = raw.split()
        if len(parts) == 2:
            return f"{parts[0]} {parts[1]}"
        elif len(raw) >= 5:
            return f"{raw[:-3]} {raw[-3:]}"
    return ""


def clean_stop_name(stop: str) -> str:
    """Strip common noise prefixes from stop names to form clean search queries."""
    s = stop.strip()
    # Strip prefixes like 'Opposite', 'Near', 'By', 'Layby', 'Outside', 'Adj', 'Adjacent to'
    patterns = [
        r"^(opposite the|opposite|opp\.?|near the|near|outside the|outside|by the|by|adj\.?|adjacent to)\s+",
        r"\s+(car park|layby|c/p)$",
    ]
    for p in patterns:
        s = re.sub(p, "", s, flags=re.IGNORECASE).strip()
    return s


def search_nominatim(query: str, delay: float = 1.0) -> list[dict[str, Any]]:
    """Query OSM Nominatim API with rate-limiting."""
    time.sleep(delay)
    url = f"https://nominatim.openstreetmap.org/search?format=json&addressdetails=1&limit=3&q={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        # Silently return empty on network hiccups
        return []


def upgrade_authority_stops(
    authority: str,
    limit: int | None = None,
    delay: float = 1.0,
    dry_run: bool = False,
    bboxes: dict[str, Any] | None = None,
    manual_pins: dict[str, Any] | None = None,
    ref_stops: dict[str, Any] | None = None,
) -> tuple[int, int]:
    """Search and upgrade stops for a given local authority."""
    slug = re.sub(r"[^a-z0-9]+", "_", authority.lower()).strip("_")
    csv_file = DATA_DIR / f"{slug}.csv"
    if not csv_file.exists():
        matches = [f for f in DATA_DIR.glob("*.csv") if normalise_key(f.stem) == normalise_key(slug)]
        if matches:
            csv_file = matches[0]
        else:
            print(f"Notice: CSV file for {authority} ({slug}.csv) not found.")
            return 0, 0

    bbox = None
    if bboxes:
        bbox = bboxes.get(slug) or bboxes.get(normalise_key(authority))

    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    upgraded = 0
    checked = 0

    for r in rows:
        stop = r.get("Stop", "").strip()
        comm = r.get("Community", "").strip()
        auth = r.get("Local authority", authority).strip()
        curr_lat_str = r.get("GeoY", "").strip()
        curr_lon_str = r.get("GeoX", "").strip()
        postcode = r.get("Postcode", "").strip()

        # Skip if stop is manually verified (protected)
        full_k = f"{normalise_key(auth)}::{normalise_key(comm)}::{normalise_key(stop)}"
        short_k = f"{normalise_key(auth)}::{normalise_key(stop)}"
        if (manual_pins and (full_k in manual_pins or short_k in manual_pins)):
            continue

        # Skip stops that are identical to community name (e.g. Village name repeated as stop name with no detail)
        if normalise_key(stop) == normalise_key(comm):
            continue

        # If already has postcode and coordinates, it's already medium/high accuracy.
        # Focus on stops that lack a postcode, or stops that have explicit named facilities
        landmark_kw = ["school", "hall", "church", "inn", "pub", "centre", "center", "street", "road", "lane", "close", "drive", "avenue", "terrace", "way"]
        has_landmark = any(kw in stop.lower() for kw in landmark_kw)

        if postcode and not has_landmark:
            continue

        checked += 1
        curr_lat = float(curr_lat_str) if curr_lat_str else None
        curr_lon = float(curr_lon_str) if curr_lon_str else None

        # Build candidate queries
        clean_s = clean_stop_name(stop)
        queries = []
        if clean_s != stop:
            queries.append(f"{clean_s}, {comm}, {auth}, UK")
        queries.append(f"{stop}, {comm}, {auth}, UK")
        queries.append(f"{comm} {clean_s}, {auth}, UK")

        match_found = None
        for q in queries:
            results = search_nominatim(q, delay=delay)
            for res in results:
                lat = float(res.get("lat", 0))
                lon = float(res.get("lon", 0))

                # Check inside council bounding box
                if bbox and not is_in_bbox(lat, lon, bbox):
                    continue

                # Check distance from existing centroid (must be within 12km)
                if curr_lat is not None and curr_lon is not None:
                    dist = haversine_km(curr_lat, curr_lon, lat, lon)
                    if dist > 12.0:
                        continue

                # Valid match
                match_found = (lat, lon, res.get("display_name", ""))
                break

            if match_found:
                break

        if match_found:
            new_lat, new_lon, disp_name = match_found
            new_lat = round(new_lat, 5)
            new_lon = round(new_lon, 5)
            new_pc = extract_postcode(disp_name)

            print(f"✓ [{auth}] {comm} - {stop}")
            print(f"  Old: ({curr_lat_str}, {curr_lon_str}) -> New: ({new_lat:.5f}, {new_lon:.5f})")
            if new_pc and not postcode:
                print(f"  Added Postcode: {new_pc}")
                r["Postcode"] = new_pc
            print(f"  Match: {disp_name[:90]}")

            r["GeoX"] = f"{new_lon:.5f}"
            r["GeoY"] = f"{new_lat:.5f}"

            # Save in reference cache
            if ref_stops is not None:
                entry = {
                    "authority": auth,
                    "community": comm,
                    "stop": stop,
                    "postcode": r.get("Postcode", ""),
                    "geox": new_lon,
                    "geoy": new_lat,
                    "source": "osm_search",
                    "accuracy": "landmark" if has_landmark else "street",
                    "updated_at": "2026-11-22",
                }
                ref_stops[full_k] = entry
                ref_stops[short_k] = entry

            upgraded += 1

        if limit and upgraded >= limit:
            break

    if upgraded > 0 and not dry_run:
        with open(csv_file, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Saved {upgraded} upgraded stop coordinates to {csv_file.name}")

    return upgraded, checked


def main() -> None:
    parser = argparse.ArgumentParser(description="Automated Coordinate Upgrader using OpenStreetMap Nominatim")
    parser.add_argument("--authority", type=str, help="Specific local authority to upgrade (e.g. leicestershire)")
    parser.add_argument("--all", action="store_true", help="Upgrade across all authorities with coarse stops")
    parser.add_argument("--limit", type=int, default=25, help="Maximum number of stops to upgrade per run")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay in seconds between requests (default 1.0s)")
    parser.add_argument("--dry-run", action="store_true", help="Preview matches without writing files")

    args = parser.parse_args()

    bboxes = load_json(BBOX_FILE)
    manual_pins = load_json(MANUAL_PINS_FILE)
    ref_stops = load_json(STOPS_REF_FILE)

    if args.authority:
        upgraded, checked = upgrade_authority_stops(
            args.authority,
            limit=args.limit,
            delay=args.delay,
            dry_run=args.dry_run,
            bboxes=bboxes,
            manual_pins=manual_pins,
            ref_stops=ref_stops,
        )
        print(f"\nDone: {upgraded} stops upgraded out of {checked} checked.")
    elif args.all:
        accuracy_csv = DATA_DIR / "uk_mobile_library_stops_accuracy.csv"
        authorities = []
        if accuracy_csv.exists():
            with open(accuracy_csv, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                import collections
                counts = collections.Counter(r["Local authority"] for r in reader if r["Accuracy tier"] == "community")
                authorities = [a for a, _ in counts.most_common()]

        total_upgraded = 0
        for auth in authorities:
            print(f"\n--- Processing {auth} ---")
            upg, _ = upgrade_authority_stops(
                auth,
                limit=args.limit,
                delay=args.delay,
                dry_run=args.dry_run,
                bboxes=bboxes,
                manual_pins=manual_pins,
                ref_stops=ref_stops,
            )
            total_upgraded += upg
            if total_upgraded >= args.limit:
                break
        print(f"\nTotal stops upgraded: {total_upgraded}")
    else:
        parser.print_help()

    # Save reference cache updates
    if not args.dry_run and STOPS_REF_FILE.exists():
        STOPS_REF_FILE.write_text(json.dumps(ref_stops, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
