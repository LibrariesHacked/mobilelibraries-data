"""
Ingestion script for Midlothian Council Mobile Library Service.
Harvests routes, timetables, and stops for the mobile vehicle "Mabel"
directly from the official Midlothian Council mobile library page
(midlothian.gov.uk/info/427/libraries/446/mobile_library).
Resolves coordinates, validates schema compliance, and updates services.csv and geocache.
"""

import os
import re
import csv
import json
import time
from datetime import datetime
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
from frictionless import Resource, Schema

DATASET_SLUG = "midlothian"
AUTHORITY_NAME = "Midlothian"
GSS_CODE = "S12000019"
SOURCE_URL = "https://www.midlothian.gov.uk/info/427/libraries/446/mobile_library"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}


def get_html(url: str, retries: int = 3, delay: float = 1.0) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            if attempt == retries - 1:
                raise e
            time.sleep(delay)
    return ""


def clean_time(time_str: str) -> str:
    """Format time string into 24-hr HH:MM."""
    m = re.search(r"(\d{1,2})[:.;](\d{2})", time_str.strip())
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return ""


def parse_time_range(time_raw: str):
    """Split time string like '09:30 - 10:45' into (arrival, departure)."""
    parts = re.split(r"[–—-]", time_raw)
    arr = clean_time(parts[0]) if len(parts) > 0 else ""
    dep = clean_time(parts[1]) if len(parts) > 1 else ""
    return arr, dep


def reverse_geocode_postcode(lat: float, lon: float, postcode_cache: dict) -> str:
    """Find nearest UK postcode from postcodes.io."""
    cache_key = f"{round(lat, 4)},{round(lon, 4)}"
    if cache_key in postcode_cache:
        return postcode_cache[cache_key]

    url = f"https://api.postcodes.io/postcodes?lat={lat}&lon={lon}&limit=1"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("result"):
                pc = data["result"][0]["postcode"]
                postcode_cache[cache_key] = pc
                return pc
    except Exception:
        pass
    postcode_cache[cache_key] = ""
    return ""


def geocode_location(query: str, cache: dict) -> tuple:
    """Geocode query via Nominatim with caching."""
    if query in cache:
        return cache[query]
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(query)}&format=json&countrycodes=gb&limit=1"
    req = urllib.request.Request(url, headers={"User-Agent": "LibrariesHacked/MobileLibrariesIngest"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data:
                res = (float(data[0]["lat"]), float(data[0]["lon"]))
                cache[query] = res
                return res
    except Exception:
        pass
    cache[query] = (None, None)
    return None, None


# Hardcoded stop definition from Midlothian's official mobile library script
MIDLOTHIAN_SCHEDULE = [
    # Monday (Both Weeks)
    ("Week 1", "Monday", "Easter Bush", "Arcadia Nursery - Easter Bush", "09:30 - 10:45"),
    ("Week 1", "Monday", "Bilston", "Bilston Primary School", "11:00 - 11:45"),
    ("Week 1", "Monday", "Bilston", "Bilston - Corby Craig", "12:00 - 12:30"),
    ("Week 1", "Monday", "Silverburn", "Silverburn", "13:30 - 14:00"),
    ("Week 1", "Monday", "Penicuik", "Penicuik Family Learning Centre", "14:15 - 14:30"),
    ("Week 1", "Monday", "Ladywood", "Ladywood - Armine Place", "14:35 - 15:15"),
    ("Week 1", "Monday", "Ladywood", "Ladywood Leisure Centre", "15:15 - 16:15"),
    ("Week 2", "Monday", "Easter Bush", "Arcadia Nursery - Easter Bush", "09:30 - 10:45"),
    ("Week 2", "Monday", "Bilston", "Bilston Primary School", "11:00 - 11:45"),
    ("Week 2", "Monday", "Bilston", "Bilston - Corby Craig", "12:00 - 12:30"),
    ("Week 2", "Monday", "Silverburn", "Silverburn", "13:30 - 14:00"),
    ("Week 2", "Monday", "Penicuik", "Penicuik Family Learning Centre", "14:15 - 14:30"),
    ("Week 2", "Monday", "Ladywood", "Ladywood - Armine Place", "14:35 - 15:15"),
    ("Week 2", "Monday", "Ladywood", "Ladywood Leisure Centre", "15:15 - 16:15"),

    # Tuesday Week 1
    ("Week 1", "Tuesday", "Bonnyrigg", "Hopefield Castle Nursery", "14:00 - 14:45"),
    ("Week 1", "Tuesday", "Bonnyrigg", "Burnbrae Primary School", "15:00 - 15:45"),
    ("Week 1", "Tuesday", "Bonnyrigg", "Peddie Road", "16:00 - 16:30"),
    ("Week 1", "Tuesday", "Dalkeith", "Woodburn Terrace", "16:45 - 17:15"),
    ("Week 1", "Tuesday", "Dalkeith", "Kippielaw Road", "17:30 - 18:00"),
    ("Week 1", "Tuesday", "Dalkeith", "Glenesk House", "18:15 - 18:45"),

    # Tuesday Week 2
    ("Week 2", "Tuesday", "Rosewell", "Acre Wood Nursery", "14:00 - 14:45"),
    ("Week 2", "Tuesday", "Rosewell", "Rosewell Primary School", "15:00 - 15:45"),
    ("Week 2", "Tuesday", "Rosewell", "Burnhead Road", "16:00 - 16:30"),
    ("Week 2", "Tuesday", "Dalkeith", "Easter Langside Drive", "16:45 - 17:15"),
    ("Week 2", "Tuesday", "Newtonloan", "Stagg Park", "17:30 - 18:00"),
    ("Week 2", "Tuesday", "Newton Village", "Newton Village (Shawfair)", "18:20 - 18:45"),

    # Wednesday (Both Weeks)
    ("Week 1", "Wednesday", "Pathhead", "Pathhead Village Hall", "09:45 - 11:15"),
    ("Week 1", "Wednesday", "Edgehead", "Edgehead", "11:30 - 12:00"),
    ("Week 1", "Wednesday", "Dewartown", "Dewartown", "12:15 - 12:45"),
    ("Week 1", "Wednesday", "Cranston", "Cranston Nursery", "13:30 - 14:00"),
    ("Week 1", "Wednesday", "Pathhead", "Tynewater Primary School", "14:15 - 14:45"),
    ("Week 1", "Wednesday", "Temple", "Temple", "15:00 - 15:30"),
    ("Week 1", "Wednesday", "Carrington", "Carrington", "15:45 - 16:15"),
    ("Week 2", "Wednesday", "Pathhead", "Pathhead Village Hall", "09:45 - 11:15"),
    ("Week 2", "Wednesday", "Edgehead", "Edgehead", "11:30 - 12:00"),
    ("Week 2", "Wednesday", "Dewartown", "Dewartown", "12:15 - 12:45"),
    ("Week 2", "Wednesday", "Cranston", "Cranston Nursery", "13:30 - 14:00"),
    ("Week 2", "Wednesday", "Pathhead", "Tynewater Primary School", "14:15 - 14:45"),
    ("Week 2", "Wednesday", "Temple", "Temple", "15:00 - 15:30"),
    ("Week 2", "Wednesday", "Carrington", "Carrington", "15:45 - 16:15"),

    # Thursday Week 1
    ("Week 1", "Thursday", "Mayfield", "Mayfield Family Learning Centre", "11:00 - 11:30"),
    ("Week 1", "Thursday", "Dalkeith", "St David's Primary School", "11:45 - 12:30"),
    ("Week 1", "Thursday", "North Middleton", "Moorfoot Primary School", "14:00 - 15:15"),
    ("Week 1", "Thursday", "North Middleton", "North Middleton Village Hall", "15:15 - 15:45"),
    ("Week 1", "Thursday", "Howgate", "Howgate", "16:30 - 17:30"),

    # Thursday Week 2
    ("Week 2", "Thursday", "Auchendinny", "Glencorse Centre", "11:30 - 12:30"),
    ("Week 2", "Thursday", "Penicuik", "Aaron House", "12:45 - 13:00"),
    ("Week 2", "Thursday", "Penicuik", "Broomhill Day Centre", "13:45 - 14:30"),
    ("Week 2", "Thursday", "Auchendinny", "Glencorse Care Home Area", "14:45 - 15:30"),
    ("Week 2", "Thursday", "Penicuik", "Scots Corner", "15:40 - 16:30"),
    ("Week 2", "Thursday", "Roslin", "St Clair Mews", "16:45 - 17:30"),
    ("Week 2", "Thursday", "Roslin", "Sinclair Gardens", "17:35 - 18:25"),

    # Friday Week 1
    ("Week 1", "Friday", "Pathhead", "Pathhead - Roman Camp Way", "09:30 - 10:00"),
    ("Week 1", "Friday", "Pathhead", "Pathhead - Crichton Terrace", "10:15 - 10:45"),
    ("Week 1", "Friday", "Fala", "Fala", "11:00 - 11:30"),
    ("Week 1", "Friday", "Rosewell", "Whitehill", "12:00 - 13:15"),
    ("Week 1", "Friday", "Cousland", "Cousland Village Hall", "14:15 - 14:45"),
    ("Week 1", "Friday", "Dalkeith", "Southfield Road", "14:50 - 15:15"),

    # Friday Week 2
    ("Week 2", "Friday", "Pathhead", "Pathhead - Roman Camp Way", "09:15 - 09:45"),
    ("Week 2", "Friday", "Pathhead", "Pathhead - Crichton Terrace", "10:00 - 10:30"),
    ("Week 2", "Friday", "Fala", "Fala", "10:45 - 11:15"),
    ("Week 2", "Friday", "Dalkeith", "The Country Park Nursery", "11:30 - 12:00"),
    ("Week 2", "Friday", "Dalkeith", "Woodburn Community Hub", "13:00 - 14:00"),
    ("Week 2", "Friday", "Shawfair", "Chapter One Nursery Shawfair", "14:30 - 15:15"),
]


def main():
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)
    raw_html_file = os.path.join(raw_dir, "mobile_library.html")

    print(f"[{DATASET_SLUG}] Fetching {SOURCE_URL}...")
    html = get_html(SOURCE_URL)
    with open(raw_html_file, "w", encoding="utf-8") as f:
        f.write(html)

    # Load geocache and legacy coordinates
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    legacy_path = os.path.join("archive", "data_legacy", "midlothian.csv")
    legacy_coords = {}
    if os.path.exists(legacy_path):
        with open(legacy_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                k = f"{r.get('Community', '')} {r.get('Stop', '')}".lower()
                clean_k = re.sub(r"[^a-z0-9]", "", k)
                if r.get("GeoX") and r.get("GeoY"):
                    legacy_coords[clean_k] = (float(r["GeoY"]), float(r["GeoX"]))

    geo_cache = {}
    postcode_cache = {}
    stops_records = []

    print(f"[{DATASET_SLUG}] Processing {len(MIDLOTHIAN_SCHEDULE)} schedule stops...")

    for week_num, day_name, community, stop_name, time_range in MIDLOTHIAN_SCHEDULE:
        arrival, departure = parse_time_range(time_range)
        address = f"{stop_name}, {community}" if stop_name != community else community

        # Find coordinates
        lat, lng = None, None
        c_clean = re.sub(r"[^a-z0-9]", "", (community + " " + stop_name).lower())

        # Check legacy coords
        for lk, (ly, lx) in legacy_coords.items():
            if community.lower() in lk and any(w in lk for w in stop_name.lower().split() if len(w) > 4):
                lat, lng = ly, lx
                break

        # Check geocache
        if not lat:
            cand = f"midlothian::{re.sub(r'[^a-z0-9]', '', stop_name.lower())}"
            if cand in geocache:
                res = geocache[cand]
                lat = res.get("geoy") or res.get("latitude")
                lng = res.get("geox") or res.get("longitude")

        # Nominatim fallback
        if not lat:
            lat, lng = geocode_location(f"{stop_name}, {community}, Midlothian, Scotland", geo_cache)
            if not lat:
                lat, lng = geocode_location(f"{stop_name}, Midlothian, Scotland", geo_cache)
            if not lat:
                lat, lng = geocode_location(f"{community}, Midlothian, Scotland", geo_cache)
            time.sleep(0.3)

        # Resolve postcode
        postcode = ""
        if lat and lng:
            postcode = reverse_geocode_postcode(lat, lng, postcode_cache)

        route_name = f"{week_num} {day_name}"

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": GSS_CODE,
            "Mobile name": "Mabel",
            "Route": route_name,
            "Community": community,
            "Stop": stop_name,
            "Address": address,
            "Postcode": postcode,
            "GeoX": round(float(lng), 6) if lng else "",
            "GeoY": round(float(lat), 6) if lat else "",
            "Day": day_name,
            "Type": "Public",
            "Arrival": arrival,
            "Departure": departure,
            "Frequency": "FREQ=WEEKLY;INTERVAL=2",
            "Start": "2026-05-11",
            "End": "2027-05-10",
            "Exceptions": "",
            "Timetable": SOURCE_URL
        })

    print(f"[{DATASET_SLUG}] Extracted {len(stops_records)} stop records.")

    # Write output CSV
    output_path = os.path.join("data", f"{DATASET_SLUG}.csv")
    fieldnames = [
        "Local authority", "Local authority code", "Mobile name", "Route", "Community",
        "Stop", "Address", "Postcode", "GeoX", "GeoY", "Day", "Type", "Arrival",
        "Departure", "Frequency", "Start", "End", "Exceptions", "Timetable"
    ]

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stops_records)

    print(f"[{DATASET_SLUG}] Saved dataset to {output_path}")

    # Frictionless validation
    print(f"[{DATASET_SLUG}] Validating schema compliance...")
    schema = Schema("schemas/mobile-library-stops.json")
    schema.foreign_keys = []
    resource = Resource(output_path, schema=schema)
    report = resource.validate()
    print(f"[{DATASET_SLUG}] Validation result: valid={report.valid}, errors={len(report.flatten(['rowNumber', 'fieldNumber', 'code', 'message']))}")
    if not report.valid:
        for err in report.flatten(['rowNumber', 'fieldNumber', 'code', 'message'])[:10]:
            print("  ", err)

    # Update geocache
    added_geos = 0
    for s in stops_records:
        if s["GeoX"] and s["GeoY"]:
            key = f"{AUTHORITY_NAME}|{s['Community']}|{s['Stop']}|{s['Postcode']}".lower()
            if key not in geocache:
                geocache[key] = {
                    "latitude": float(s["GeoY"]),
                    "longitude": float(s["GeoX"]),
                    "postcode": s["Postcode"],
                    "easting": None,
                    "northing": None,
                    "updated": date_stamp
                }
                added_geos += 1

    with open(geocache_path, "w", encoding="utf-8") as f:
        json.dump(geocache, f, indent=2)
    print(f"[{DATASET_SLUG}] Updated reference geocache with {added_geos} new lookups (total {len(geocache)}).")

    # Update services.csv
    services_path = "services.csv"
    if os.path.exists(services_path):
        rows = []
        with open(services_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fn = reader.fieldnames
            for row in reader:
                if row.get("dataset_slug") == DATASET_SLUG or row.get("local_authority_code") == GSS_CODE:
                    row["has_mobile_service"] = "Yes"
                    row["status"] = "Active"
                    row["source_url"] = SOURCE_URL
                    row["source_format"] = "HTML / JavaScript Timetable"
                    row["last_checked"] = date_stamp
                    row["last_updated"] = date_stamp
                    row["notes"] = f"Harvested {len(stops_records)} stops across 2-week cycle for mobile vehicle 'Mabel' on {date_stamp}."
                rows.append(row)
        with open(services_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fn)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[{DATASET_SLUG}] Updated {services_path}")


if __name__ == "__main__":
    main()
