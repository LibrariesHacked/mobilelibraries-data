"""Manual Geocoding and Coordinate Verification Tool.

Allows manual inspection, review, and pin-dropping (e.g. from Google Maps or Street View)
for mobile library stops. Manually verified pins are saved to geocache/manual_pins.json,
permanently protecting them from being overwritten by automated scrapers.

Usage:
  python scripts/manual_geocode.py --export-queue
  python scripts/manual_geocode.py --import-queue data/geocoding_review_queue.csv
  python scripts/manual_geocode.py --update --authority conwy --stop "Parish Hall Car Park" --lat 53.02340 --lon -3.56120 --notes "Checked on Street View"
  python scripts/manual_geocode.py --review [--limit 10]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import describe_frequency

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
GEOCACHE_DIR = ROOT / "geocache"
MANUAL_PINS_FILE = GEOCACHE_DIR / "manual_pins.json"
BBOX_FILE = GEOCACHE_DIR / "authority_bboxes.json"
STOPS_REF_FILE = GEOCACHE_DIR / "stops_reference.json"


def normalise_key(text: str) -> str:
    """Lowercase text and strip non-alphanumeric characters."""
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def load_manual_pins() -> dict[str, Any]:
    """Load manually verified pins from geocache/manual_pins.json."""
    if MANUAL_PINS_FILE.exists():
        try:
            return json.loads(MANUAL_PINS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_manual_pins(pins: dict[str, Any]) -> None:
    """Save manually verified pins to geocache/manual_pins.json."""
    GEOCACHE_DIR.mkdir(parents=True, exist_ok=True)
    MANUAL_PINS_FILE.write_text(json.dumps(pins, indent=2), encoding="utf-8")


def load_bboxes() -> dict[str, Any]:
    """Load authority bounding boxes."""
    if BBOX_FILE.exists():
        try:
            return json.loads(BBOX_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def get_authority_bbox(authority: str, bboxes: dict[str, Any]) -> dict[str, float] | None:
    """Look up bounding box for an authority name."""
    if not authority:
        return None
    slug = re.sub(r"[^a-z0-9]+", "_", authority.lower()).strip("_")
    if slug in bboxes:
        return bboxes[slug]
    norm = normalise_key(authority)
    for k, v in bboxes.items():
        if normalise_key(k) == norm or normalise_key(k) in norm or norm in normalise_key(k):
            return v
    return None


def is_in_bbox(lat: float, lon: float, bbox: dict[str, float] | None) -> bool:
    """Return True if coordinates fall within the authority bounding box."""
    if not bbox:
        return True
    return (bbox.get("min_lat", -90) <= lat <= bbox.get("max_lat", 90) and
            bbox.get("min_lon", -180) <= lon <= bbox.get("max_lon", 180))


def apply_manual_pin(authority: str, community: str, stop: str, lat: float, lon: float,
                     postcode: str = "", notes: str = "", source: str = "manual_street_view") -> dict[str, Any]:
    """Record a manual pin, protect it in manual_pins.json, and update the authority CSV."""
    pins = load_manual_pins()
    bboxes = load_bboxes()
    bbox = get_authority_bbox(authority, bboxes)

    lat = round(float(lat), 5)
    lon = round(float(lon), 5)

    if bbox and not is_in_bbox(lat, lon, bbox):
        print(f"Warning: Coordinates ({lat}, {lon}) fall outside the bounding box for {authority}!")

    auth_k = normalise_key(authority)
    comm_k = normalise_key(community)
    stop_k = normalise_key(stop)
    full_k = f"{auth_k}::{comm_k}::{stop_k}"
    short_k = f"{auth_k}::{stop_k}"

    entry = {
        "authority": authority,
        "community": community,
        "stop": stop,
        "postcode": postcode,
        "geox": lon,
        "geoy": lat,
        "source": source,
        "accuracy": "exact",
        "verified": True,
        "notes": notes,
        "updated_at": "2026-11-22"
    }

    pins[full_k] = entry
    if short_k not in pins:
        pins[short_k] = entry
    save_manual_pins(pins)

    # Also update stops_reference.json
    if STOPS_REF_FILE.exists():
        try:
            ref = json.loads(STOPS_REF_FILE.read_text(encoding="utf-8"))
            ref[full_k] = entry
            ref[short_k] = entry
            STOPS_REF_FILE.write_text(json.dumps(ref, indent=2), encoding="utf-8")
        except Exception:
            pass

    # Update authority CSV
    update_authority_csv(authority, stop, lat, lon, community)
    print(f"✓ Successfully locked manual pin for [{authority}] {community} - {stop}: {lat}, {lon}")
    return entry


def update_authority_csv(authority: str, stop: str, lat: float, lon: float, community: str = "") -> bool:
    """Find and update the coordinates in data/<slug>.csv."""
    # Try finding the authority file
    slug = re.sub(r"[^a-z0-9]+", "_", authority.lower()).strip("_")
    csv_file = DATA_DIR / f"{slug}.csv"
    if not csv_file.exists():
        matches = [f for f in DATA_DIR.glob("*.csv") if normalise_key(f.stem) in normalise_key(authority)]
        if matches:
            csv_file = matches[0]
        else:
            print(f"Notice: Could not locate CSV file for authority {authority}")
            return False

    rows = []
    fieldnames = []
    matched_count = 0
    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for r in reader:
            stop_match = normalise_key(r.get("Stop", "")) == normalise_key(stop)
            comm_match = not community or normalise_key(r.get("Community", "")) == normalise_key(community)
            if stop_match and comm_match:
                r["GeoX"] = f"{lon:.5f}"
                r["GeoY"] = f"{lat:.5f}"
                matched_count += 1
            rows.append(r)

    if matched_count > 0:
        with open(csv_file, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"✓ Updated {matched_count} stop row(s) in {csv_file.name}")
        return True
    return False


def determine_accuracy_tier(row: dict[str, str], manual_pins: dict[str, Any]) -> tuple[str, str, int, str]:
    """Determine accuracy tier, source, estimated error radius, and review priority."""
    auth = row.get("Local authority", "")
    comm = row.get("Community", "")
    stop = row.get("Stop", "")
    pc = row.get("Postcode", "").strip().upper()

    auth_k = normalise_key(auth)
    comm_k = normalise_key(comm)
    stop_k = normalise_key(stop)

    full_k = f"{auth_k}::{comm_k}::{stop_k}"
    short_k = f"{auth_k}::{stop_k}"

    if full_k in manual_pins or short_k in manual_pins:
        return "exact", "manual_verified", 5, "Low"

    # Check authority GIS (Shropshire, Lancashire, Essex, etc.)
    gis_authorities = {"shropshire", "lancashire", "essex", "norfolk", "bath_and_north_east_somerset"}
    auth_slug = re.sub(r"[^a-z0-9]+", "_", auth.lower()).strip("_")
    if auth_slug in gis_authorities:
        return "exact", "council_gis", 10, "Low"

    # Check if stop name clearly specifies a landmark
    landmark_keywords = ["hall", "school", "pub", "inn", "church", "centre", "center", "car park", "surgery"]
    has_landmark_name = any(kw in stop.lower() or kw in row.get("Address", "").lower() for kw in landmark_keywords)

    if pc:
        if has_landmark_name:
            return "landmark", "named_facility", 25, "Medium"
        return "postcode", "postcode_centroid", 100, "Medium"

    if has_landmark_name:
        return "landmark", "community_facility", 50, "High"

    return "community", "settlement_centroid", 1000, "High"


def export_review_queue(output_path: Path) -> None:
    """Export all stops prioritized by review need into a CSV spreadsheet."""
    stops_file = DATA_DIR / "uk_mobile_library_stops.csv"
    if not stops_file.exists():
        print(f"Error: {stops_file} does not exist. Run scripts/combine.py first.")
        return

    manual_pins = load_manual_pins()
    with open(stops_file, mode="r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    queue = []
    for r in rows:
        auth = r.get("Local authority", "")
        comm = r.get("Community", "")
        stop = r.get("Stop", "")
        addr = r.get("Address", "")
        pc = r.get("Postcode", "")
        lat = r.get("GeoY", "")
        lon = r.get("GeoX", "")
        freq_raw = r.get("Frequency", "")
        visit_freq = describe_frequency(freq_raw)

        tier, source, radius_m, priority = determine_accuracy_tier(r, manual_pins)

        # Build helpful Google search and Street View URLs
        query = f"{stop}, {comm}, {pc}, {auth}, UK".strip(", ")
        gmaps_search = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(query)}"
        streetview_link = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}" if lat and lon else ""

        queue.append({
            "review_priority": priority,
            "accuracy_tier": tier,
            "estimated_radius_m": radius_m,
            "local_authority": auth,
            "community": comm,
            "stop": stop,
            "address": addr,
            "postcode": pc,
            "visit_frequency": visit_freq,
            "current_latitude": lat,
            "current_longitude": lon,
            "geocoding_source": source,
            "google_maps_search": gmaps_search,
            "streetview_link": streetview_link,
            "new_latitude": "",
            "new_longitude": "",
            "notes": ""
        })

    # Sort high priority first, then medium, then low
    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    queue.sort(key=lambda q: (priority_order.get(q["review_priority"], 3), q["local_authority"], q["community"]))

    fieldnames = [
        "review_priority", "accuracy_tier", "estimated_radius_m", "local_authority",
        "community", "stop", "address", "postcode", "visit_frequency", "current_latitude", "current_longitude",
        "geocoding_source", "google_maps_search", "streetview_link",
        "new_latitude", "new_longitude", "notes"
    ]

    with open(output_path, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(queue)

    high_c = sum(1 for q in queue if q["review_priority"] == "High")
    med_c = sum(1 for q in queue if q["review_priority"] == "Medium")
    low_c = sum(1 for q in queue if q["review_priority"] == "Low")
    print(f"✓ Exported {len(queue)} stops to {output_path}")
    print(f"  Priority breakdown: High={high_c} (community level), Medium={med_c} (postcode level), Low={low_c} (verified/exact)")


def import_review_queue(queue_path: Path) -> None:
    """Import user-completed coordinates from a review spreadsheet and lock them as manual pins."""
    if not queue_path.exists():
        print(f"Error: {queue_path} does not exist.")
        return

    with open(queue_path, mode="r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    updated_count = 0
    for r in rows:
        new_lat = r.get("new_latitude", "").strip()
        new_lon = r.get("new_longitude", "").strip()
        if new_lat and new_lon:
            try:
                lat = float(new_lat)
                lon = float(new_lon)
                auth = r.get("local_authority", "")
                comm = r.get("community", "")
                stop = r.get("stop", "")
                pc = r.get("postcode", "")
                notes = r.get("notes", "") or "Imported from review queue"
                apply_manual_pin(auth, comm, stop, lat, lon, pc, notes=notes)
                updated_count += 1
            except ValueError:
                print(f"Invalid coordinate: lat='{new_lat}', lon='{new_lon}' for stop {r.get('stop')}")

    print(f"✓ Successfully imported and locked {updated_count} manual pins.")


def interactive_review(limit: int = 10) -> None:
    """Interactive console session walking through top high-priority stops."""
    stops_file = DATA_DIR / "uk_mobile_library_stops.csv"
    if not stops_file.exists():
        print("Run scripts/combine.py first.")
        return

    manual_pins = load_manual_pins()
    with open(stops_file, mode="r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    high_priority = []
    for r in rows:
        tier, source, radius, priority = determine_accuracy_tier(r, manual_pins)
        if priority == "High":
            high_priority.append(r)

    print(f"\nFound {len(high_priority)} High-priority stops needing manual review.")
    print(f"Showing up to {limit} stops. Press Enter without typing coordinates to skip.\n")

    for i, r in enumerate(high_priority[:limit], start=1):
        auth = r.get("Local authority", "")
        comm = r.get("Community", "")
        stop = r.get("Stop", "")
        addr = r.get("Address", "")
        pc = r.get("Postcode", "")
        lat = r.get("GeoY", "")
        lon = r.get("GeoX", "")

        query = f"{stop}, {comm}, {pc}, {auth}, UK".strip(", ")
        gmaps = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(query)}"
        streetview = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}" if lat and lon else ""

        print(f"[{i}/{min(limit, len(high_priority))}] {auth} | {comm} - {stop}")
        if addr:
            print(f"  Address:  {addr}")
        if pc:
            print(f"  Postcode: {pc}")
        print(f"  Current:  {lat}, {lon} (Estimated radius: ~1km)")
        print(f"  Map link: {gmaps}")
        if streetview:
            print(f"  Street View: {streetview}")

        val = input("  Enter 'lat, lon' or notes (or press Enter to skip): ").strip()
        if val:
            coords = re.findall(r"[-+]?\d*\.\d+|\d+", val)
            if len(coords) >= 2:
                apply_manual_pin(auth, comm, stop, float(coords[0]), float(coords[1]), pc, notes="Terminal review")
            else:
                print("  Skipped (coordinates not recognized).")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual Geocoding and Verification Tool")
    parser.add_argument("--export-queue", action="store_true", help="Export review queue to data/geocoding_review_queue.csv")
    parser.add_argument("--import-queue", type=str, help="Import completed coordinates from a CSV spreadsheet")
    parser.add_argument("--review", action="store_true", help="Start interactive review in terminal")
    parser.add_argument("--limit", type=int, default=10, help="Number of stops to review in terminal session")
    parser.add_argument("--update", action="store_true", help="Update a single stop directly")
    parser.add_argument("--authority", type=str, help="Council / authority name")
    parser.add_argument("--community", type=str, default="", help="Community / village name")
    parser.add_argument("--stop", type=str, help="Stop name")
    parser.add_argument("--lat", type=float, help="Latitude")
    parser.add_argument("--lon", type=float, help="Longitude")
    parser.add_argument("--postcode", type=str, default="", help="Postcode")
    parser.add_argument("--notes", type=str, default="Manual verification", help="Verification notes")

    args = parser.parse_args()

    if args.export_queue:
        export_review_queue(DATA_DIR / "geocoding_review_queue.csv")
    elif args.import_queue:
        import_review_queue(Path(args.import_queue))
    elif args.update:
        if not args.authority or not args.stop or args.lat is None or args.lon is None:
            print("Error: --update requires --authority, --stop, --lat, and --lon")
            return
        apply_manual_pin(args.authority, args.community, args.stop, args.lat, args.lon, args.postcode, notes=args.notes)
    elif args.review:
        interactive_review(limit=args.limit)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
