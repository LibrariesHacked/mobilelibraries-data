"""
Ingestion script for West Dunbartonshire Council Mobile Library Service.
Harvests timetables and stops from official Council page
(west-dunbarton.gov.uk/libraries/mobile-home-delivery-services/mobile-library-service),
matches pre-geocoded legacy coordinates, resolves postcodes via postcodes.io,
validates schema compliance, and updates services.csv and geocache.
"""

from _common import get_html, reverse_geocode_postcode
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

DATASET_SLUG = "west_dunbartonshire"
AUTHORITY_NAME = "West Dunbartonshire"
GSS_CODE = "S12000039"
SOURCE_URL = "https://www.west-dunbarton.gov.uk/libraries/mobile-home-delivery-services/mobile-library-service"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}




def parse_time_range_12h(time_str: str) -> tuple:
    """Convert 12-hr time strings like '9.30-9.50am' or '1.30-1.50pm' to 24-hr (HH:MM, HH:MM)."""
    t = time_str.strip().lower()
    is_pm = "pm" in t
    t = t.replace("am", "").replace("pm", "").strip()
    parts = re.split(r"[-–—]", t)

    def to_24h(val, force_pm=False):
        """Parse an H.MM or HH:MM token into 24-hour HH:MM format, applying a 12-hour PM offset if needed."""
        m = re.search(r"(\d{1,2})[.:](\d{2})", val.strip())
        if not m:
            return ""
        h, mn = int(m.group(1)), int(m.group(2))
        if force_pm and h < 12:
            h += 12
        elif not force_pm and is_pm and h < 12:
            h += 12
        return f"{h:02d}:{mn:02d}"

    arr = to_24h(parts[0], force_pm=is_pm)
    dep = to_24h(parts[1], force_pm=is_pm) if len(parts) > 1 else ""
    return arr, dep




def main():
    """Harvest West Dunbartonshire timetable tables, match coordinates, write data/west_dunbartonshire.csv, and update metadata."""
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)
    raw_html_file = os.path.join(raw_dir, "mobile_library_service.html")

    print(f"[{DATASET_SLUG}] Fetching {SOURCE_URL}...")
    html = get_html(SOURCE_URL)
    with open(raw_html_file, "w", encoding="utf-8") as f:
        f.write(html)

    soup = BeautifulSoup(html, "html.parser")

    # Load geocache and legacy coordinates
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    legacy_path = os.path.join("archive", "data_legacy", "west_dunbartonshire.csv")
    legacy_coords = {}
    if os.path.exists(legacy_path):
        with open(legacy_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                k = f"{r.get('Community', '')} {r.get('Stop', '')}".lower()
                clean_k = re.sub(r"[^a-z0-9]", "", k)
                if r.get("GeoX") and r.get("GeoY"):
                    legacy_coords[clean_k] = (float(r["GeoY"]), float(r["GeoX"]), r.get("Community", ""))

    postcode_cache = {}
    stops_records = []

    days_list = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    tables = soup.find_all("table")
    print(f"[{DATASET_SLUG}] Found {len(tables)} day tables.")

    for idx, tbl in enumerate(tables):
        day_name = days_list[idx] if idx < len(days_list) else "Monday"
        prev_h = tbl.find_previous(["h4"])
        raw_route = prev_h.get_text(strip=True) if prev_h else day_name
        # e.g. "Monday – Bonhill, Haldane, Gartocharn and Lomondgate" -> "Bonhill, Haldane, Gartocharn and Lomondgate"
        route_clean = re.sub(r"^[A-Za-z]+\s*[-–—]\s*", "", raw_route)

        for tr in tbl.find_all("tr")[1:]:
            tds = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if len(tds) < 2 or not tds[0] or not tds[1]:
                continue

            raw_loc = tds[0].replace("\xa0", " ").strip()
            raw_time = tds[1].replace("\xa0", " ").strip()

            arrival, departure = parse_time_range_12h(raw_time)

            # Match coordinates
            lat, lng = None, None
            matched_community = route_clean.split(",")[0].strip()

            clean_loc = re.sub(r"[^a-z0-9]", "", raw_loc.lower())

            # Specific overrides for slight naming variations
            if "43" in clean_loc and "ohare" in clean_loc:
                lat, lng = 55.981985, -4.56515
                matched_community = "Bonhill & Haldane"
            elif "glencairn" in clean_loc:
                lat, lng = 55.952500, -4.562100
                matched_community = "Dumbarton"
            elif "cordale" in clean_loc:
                lat, lng = 55.973400, -4.582800
                matched_community = "Renton"
            elif "kindergarden" in clean_loc or "kindergarten" in clean_loc:
                lat, lng = 55.926500, -4.437200
                matched_community = "Duntocher"

            if not lat:
                for lk, (ly, lx, lcomm) in legacy_coords.items():
                    # Ignore short words (< 5 chars) to prevent false-positive fuzzy matches
                    if clean_loc in lk or any(w in lk for w in raw_loc.lower().split() if len(w) > 4):
                        lat, lng = ly, lx
                        matched_community = lcomm
                        break

            if not lat:
                cand = f"westdunbartonshire::{clean_loc}"
                if cand in geocache:
                    res = geocache[cand]
                    lat = res.get("geoy") or res.get("latitude")
                    lng = res.get("geox") or res.get("longitude")

            postcode = ""
            if lat and lng:
                postcode = reverse_geocode_postcode(lat, lng, postcode_cache)

            stop_name = raw_loc
            address = f"{stop_name}, {matched_community}"

            stops_records.append({
                "Local authority": AUTHORITY_NAME,
                "Local authority code": GSS_CODE,
                "Mobile name": "West Dunbartonshire Mobile Library",
                "Route": f"{day_name} - {route_clean}",
                "Community": matched_community,
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
                "Start": "2026-01-05",
                "End": "2026-12-31",
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
    # Skip foreign key validation against external reference tables
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
                    row["source_format"] = "HTML / Web Table"
                    row["last_checked"] = date_stamp
                    row["last_updated"] = date_stamp
                    row["notes"] = f"Harvested {len(stops_records)} stops across 5 routes from official Council page on {date_stamp}."
                rows.append(row)
        with open(services_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fn)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[{DATASET_SLUG}] Updated {services_path}")


if __name__ == "__main__":
    main()
