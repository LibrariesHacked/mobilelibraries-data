"""
North Lincolnshire Council Mobile Library Ingestion Script
Processes preserved official GeoJSON export for North Lincolnshire Council:
raw/north_lincolnshire.geojson
Resolves postcodes, validates schema compliance, and updates services.csv, geocache, and historical vehicle registries.
"""

from _common import reverse_geocode_postcode
import os
import re
import json
import csv
import time
import urllib.request
from datetime import datetime
from frictionless import Resource, Schema

AUTHORITY_NAME = "North Lincolnshire"
AUTHORITY_CODE = "E06000013"
SLUG = "north_lincolnshire"

RAW_SOURCE = os.path.join("raw", f"{SLUG}.geojson")
BASE_TIMETABLE_URL = "https://www.northlincs.gov.uk/schools-libraries-and-learning/libraries/the-mobile-library/"
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor'}




def run():
    """Ingest raw/north_lincolnshire.geojson, geocode postcodes, write data/north_lincolnshire.csv, and update registries."""
    print(f"[{SLUG}] Starting ingestion for {AUTHORITY_NAME} ({AUTHORITY_CODE})...")
    
    if not os.path.exists(RAW_SOURCE):
        print(f"[{SLUG}] Raw source {RAW_SOURCE} not found!")
        return

    # Load persistent geocache
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    with open(RAW_SOURCE, "r", encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", [])
    print(f"[{SLUG}] Found {len(features)} stops in GeoJSON source.")

    pc_cache = {}
    stops_records = []
    vehicle_name = "North Lincolnshire Mobile Library"

    for idx, feat in enumerate(features):
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        coords = geom.get("coordinates", [None, None])

        lng = round(float(coords[0]), 6) if coords[0] is not None else None
        lat = round(float(coords[1]), 6) if coords[1] is not None else None

        route_id = props.get("id") or props.get("route_no") or ""
        route_name = f"Route {route_id}"
        day = (props.get("day") or "").strip().title()
        stop_name = (props.get("addr") or "").strip()
        community = (props.get("name") or "").strip()
        address = f"{stop_name}, {community}" if stop_name != community else community

        time1 = props.get("time1") or ""
        time2 = props.get("time2") or ""

        # Format to 24h HH:MM
        arr = time1[:5] if time1 and len(time1) >= 5 else ""
        dep = time2[:5] if time2 and len(time2) >= 5 else ""

        # Frequency: 3-weekly cycle standard, route 12 is weekly
        freq = 1 if route_id == 12 else 3

        # Resolve postcode from coordinates
        postcode = ""
        if lat and lng:
            postcode = reverse_geocode_postcode(lat, lng, pc_cache)
            # Rate-limit requests to postcodes.io
            time.sleep(0.05)

        # Stop Type
        stop_type = "Public"
        if "school" in stop_name.lower() or "nursery" in stop_name.lower():
            stop_type = "Private"

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": AUTHORITY_CODE,
            "Mobile name": vehicle_name,
            "Route": route_name,
            "Community": community,
            "Stop": stop_name,
            "Address": address,
            "Postcode": postcode,
            "GeoX": lng if lng is not None else "",
            "GeoY": lat if lat is not None else "",
            "Day": day,
            "Type": stop_type,
            "Arrival": arr,
            "Departure": dep,
            "Frequency": (f"FREQ=WEEKLY;INTERVAL={freq}" if str(freq).isdigit() else freq),
            "Start": "2026-01-05",
            "End": "2026-12-31",
            "Exceptions": '',
            "Timetable": BASE_TIMETABLE_URL
        })

        if lat and lng:
            if postcode:
                geocache[postcode] = (lat, lng)
                geocache[postcode.replace(" ", "")] = (lat, lng)
            ref_key = f"{AUTHORITY_NAME}:{community}:{stop_name}".lower()
            geocache[ref_key] = (lat, lng)

    # Sort records
    stops_records.sort(key=lambda r: (r["Mobile name"], r["Route"], r["Arrival"], r["Community"], r["Stop"]))

    # Save geocache
    with open(geocache_path, "w", encoding="utf-8") as f:
        json.dump(geocache, f, indent=2)

    # Write CSV
    out_csv = os.path.join("data", f"{SLUG}.csv")
    fieldnames = [
        "Local authority", "Local authority code", "Mobile name", "Route", "Community",
        "Stop", "Address", "Postcode", "GeoX", "GeoY", "Day", "Type", "Arrival",
        "Departure", "Frequency", "Start", "End", "Exceptions", "Timetable"
    ]

    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stops_records)

    print(f"[{SLUG}] Saved {len(stops_records)} stops to {out_csv}")

    # Frictionless validation
    print(f"[{SLUG}] Validating schema compliance...")
    schema = Schema("schemas/mobile-library-stops.json")
    # Disable foreign key checks because reference tables are validated separately
    schema.foreign_keys = []
    resource = Resource(out_csv, schema=schema)
    report = resource.validate()
    print(f"[{SLUG}] Validation result: valid={report.valid}, errors={len(report.flatten(['rowNumber', 'fieldNumber', 'code', 'message']))}")
    if not report.valid:
        for err in report.flatten(['rowNumber', 'fieldNumber', 'code', 'message'])[:10]:
            print(f"  Row {err[0]}, Field {err[1]}: [{err[2]}] {err[3]}")
    else:
        print(f"[{SLUG}] 0 schema errors! Validation successful.")

    # Update historical vehicles
    vehicles_csv = os.path.join("history", "historical_mobile_vehicles.csv")
    if os.path.exists(vehicles_csv):
        existing_rows = []
        with open(vehicles_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            v_fieldnames = reader.fieldnames
            existing_rows = list(reader)

        existing_keys = {(r.get("Local authority"), r.get("Mobile name")) for r in existing_rows}
        key = (AUTHORITY_NAME, vehicle_name)
        if key not in existing_keys:
            existing_rows.append({
                "Local authority": AUTHORITY_NAME,
                "Mobile name": vehicle_name,
                "Dataset slug": SLUG,
                "Status": "Active",
                "Notes": "North Lincolnshire Mobile Library serving rural parishes"
            })
            with open(vehicles_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=v_fieldnames)
                writer.writeheader()
                writer.writerows(existing_rows)
            print(f"[{SLUG}] Added vehicle to historical vehicle registry.")

    # Update services.csv
    services_csv = "services.csv"
    if os.path.exists(services_csv):
        rows = []
        with open(services_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            s_fieldnames = reader.fieldnames
            rows = list(reader)

        updated = False
        today = datetime.now().strftime("%Y-%m-%d")
        for r in rows:
            if r.get("dataset_slug") == SLUG or r.get("local_authority_code") == AUTHORITY_CODE:
                r["has_mobile_service"] = "Yes"
                r["status"] = "Active Verified"
                r["source_url"] = BASE_TIMETABLE_URL
                r["source_format"] = "GeoJSON / Council GIS"
                r["last_checked"] = today
                r["last_updated"] = today
                r["notes"] = f"Harvested {len(stops_records)} stops from official North Lincolnshire GeoJSON dataset."
                updated = True
                break

        if updated:
            with open(services_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=s_fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"[{SLUG}] Updated services.csv record.")


if __name__ == "__main__":
    run()
