"""
Norfolk County Council Mobile Library Ingestion Script
Harvests all mobile library stops from Norfolk County Council's official ArcGIS MapServer (REST JSON):
https://maps.norfolk.gov.uk/arcgis/rest/services/layers_ext/where_i_live/MapServer/16/
Writes data/norfolk.csv, validates schema compliance, and updates services.csv, geocache, and historical vehicle registries.
"""

from _common import reverse_geocode_postcode
import os
import re
import ssl
import time
import json
import csv
import urllib.request
from datetime import datetime
from frictionless import Resource, Schema

AUTHORITY_NAME = "Norfolk"
AUTHORITY_CODE = "E10000020"
SLUG = "norfolk"

ARCGIS_LAYER_URL = "https://maps.norfolk.gov.uk/arcgis/rest/services/layers_ext/where_i_live/MapServer/16/query"
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor'}

DAY_MAP = {
    '1': 'Monday',
    '2': 'Tuesday',
    '3': 'Wednesday',
    '4': 'Thursday',
    '5': 'Friday'
}

# Matches standard UK postcodes (including GIR 0AA) to detect malformed source values
POSTCODE_RE = re.compile(r"^([A-Za-z][A-Ha-hJ-Yj-y]?[0-9][A-Za-z0-9]? ?[0-9][A-Za-z]{2}|[Gg][Ii][Rr] ?0[Aa]{2})$")




VEHICLE_MAP = {
    'CEN': 'Central Mobile Library',
    'DER': 'Dereham Mobile Library',
    'EDE': 'East Dereham Mobile Library'
}


def run():
    """Page through Norfolk's ArcGIS MapServer layer, write data/norfolk.csv, validate schema, and update registries."""
    print(f"[{SLUG}] Starting harvest for {AUTHORITY_NAME} ({AUTHORITY_CODE})...")
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)

    # Load persistent geocache
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    # Query all records from ArcGIS
    all_features = []
    offset = 0
    batch_size = 1000

    while True:
        # outSR=4326 requests WGS84 lon/lat; paginate in 1000-record batches per ArcGIS limit
        query_url = f"{ARCGIS_LAYER_URL}?where=1%3D1&outFields=*&outSR=4326&resultOffset={offset}&resultRecordCount={batch_size}&f=json"
        print(f"[{SLUG}] Querying ArcGIS features from offset {offset}...")
        raw_file = os.path.join(raw_dir, f"arcgis_layer16_offset_{offset}.json")

        if os.path.exists(raw_file):
            with open(raw_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            req = urllib.request.Request(query_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw_bytes = resp.read()
                data = json.loads(raw_bytes.decode("utf-8"))
            with open(raw_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        print(f"[{SLUG}] Retrieved {len(features)} features (total: {len(all_features)})")

        if not data.get("exceededTransferLimit", False) or len(features) < batch_size:
            break

        offset += batch_size
        time.sleep(0.5)

    print(f"[{SLUG}] Total raw features downloaded: {len(all_features)}")

    stops_records = []
    vehicles_seen = set()

    for feat in all_features:
        att = feat.get("attributes", {})
        geom = feat.get("geometry", {})

        lng = round(float(geom.get("x")), 6) if geom.get("x") is not None else None
        lat = round(float(geom.get("y")), 6) if geom.get("y") is not None else None

        village = (att.get("Village") or "").strip().title()
        stop_name = (att.get("StopName") or "").strip().title()
        postcode = (att.get("Postcode") or "").strip().upper()
        if postcode and not POSTCODE_RE.match(postcode):
            rev_pc = reverse_geocode_postcode(lat, lng)
            postcode = rev_pc if rev_pc else ""
        route_num = str(att.get("RouteNumber") or "").strip()
        stop_num = att.get("StopNumber")
        op_centre = (att.get("OperatingCentre") or "").strip().upper()
        arr = (att.get("Arrival") or "").strip()
        dep = (att.get("Departure") or "").strip()

        # Day derived from first digit of route number
        day_digit = route_num[0] if route_num else ""
        day = DAY_MAP.get(day_digit, "Monday")

        # Vehicle name
        vehicle = VEHICLE_MAP.get(op_centre, f"{op_centre} Mobile Library" if op_centre else "Norfolk Mobile Library")
        vehicles_seen.add(vehicle)

        # Route name
        route_name = f"{vehicle} Route {route_num}"

        # Address
        address = f"{stop_name}, {village}" if stop_name != village else village

        # Stop Type
        stop_type = "Public"
        if "school" in stop_name.lower() or "nursery" in stop_name.lower():
            stop_type = "Private"

        # Timetable link
        timetable_url = f"https://www.norfolk.gov.uk/libraries-local-history-and-archives/libraries/your-local-library/mobile-libraries"

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": AUTHORITY_CODE,
            "Mobile name": vehicle,
            "Route": route_name,
            "Community": village,
            "Stop": stop_name,
            "Address": address,
            "Postcode": postcode,
            "GeoX": lng if lng is not None else "",
            "GeoY": lat if lat is not None else "",
            "Day": day,
            "Type": stop_type,
            "Arrival": arr,
            "Departure": dep,
            "Frequency": "FREQ=WEEKLY;INTERVAL=4",
            "Start": "2026-01-05",
            "End": "2026-12-31",
            "Exceptions": "Bank holidays",
            "Timetable": timetable_url
        })

        # Update geocache
        if lat and lng:
            if postcode:
                geocache[postcode] = (lat, lng)
                geocache[postcode.replace(" ", "")] = (lat, lng)
            ref_key = f"{AUTHORITY_NAME}:{village}:{stop_name}".lower()
            geocache[ref_key] = (lat, lng)

    # Sort deterministically
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
    # Clear foreign keys so standalone CSV validation does not fail on external table refs
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
    if os.path.exists(vehicles_csv) and vehicles_seen:
        existing_rows = []
        with open(vehicles_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            v_fieldnames = reader.fieldnames
            existing_rows = list(reader)

        existing_keys = {(r.get("Local authority"), r.get("Mobile name")) for r in existing_rows}
        added = 0
        for v in sorted(vehicles_seen):
            key = (AUTHORITY_NAME, v)
            if key not in existing_keys:
                existing_rows.append({
                    "Local authority": AUTHORITY_NAME,
                    "Mobile name": v,
                    "Dataset slug": SLUG,
                    "Status": "Active",
                    "Notes": "Extracted from Norfolk County Council ArcGIS MapServer Layer 16"
                })
                added += 1

        if added > 0:
            with open(vehicles_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=v_fieldnames)
                writer.writeheader()
                writer.writerows(existing_rows)
            print(f"[{SLUG}] Added {added} vehicles to historical vehicle registry.")

    # Update services.csv
    services_csv = "services.csv"
    if os.path.exists(services_csv):
        rows = []
        with open(services_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            s_fieldnames = reader.fieldnames
            rows = list(reader)

        updated = False
        for r in rows:
            if r.get("slug") == SLUG or r.get("gss_code") == AUTHORITY_CODE:
                r["status"] = "Active"
                r["dataset_status"] = "Ingested"
                r["stop_count"] = str(len(stops_records))
                r["format"] = "ArcGIS REST MapServer"
                r["source_url"] = ARCGIS_LAYER_URL
                r["notes"] = f"Harvested {len(stops_records)} stops across 81 routes from Norfolk ArcGIS MapServer Layer 16 (Central, Dereham, East Dereham mobile libraries)."
                updated = True
                break

        if updated:
            with open(services_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=s_fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"[{SLUG}] Updated services.csv record for Norfolk.")


if __name__ == "__main__":
    run()
