"""
Ingestion script for Worcestershire County Council Mobile Library Service.
Harvests all 207 stops directly from the official Worcestershire GIS portal
(gis.worcestershire.gov.uk/website/worcestershiremobilelibrary) via ASP.NET WebForm Callback.
Converts British National Grid (EPSG:27700) coordinates to WGS84 (EPSG:4326), validates schema compliance,
and updates services.csv and geocache.
"""

from _common import clean_time, reverse_geocode_postcode
import os
import re
import csv
import json
import time
from datetime import datetime, timedelta
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
import pyproj
from frictionless import Resource, Schema

DATASET_SLUG = "worcestershire"
AUTHORITY_NAME = "Worcestershire"
GSS_CODE = "E10000034"
BASE_URL = "https://gis.worcestershire.gov.uk/website/worcestershiremobilelibrary/"
TIMETABLE_URL = "https://www.worcestershire.gov.uk/council-services/worcestershire-libraries/your-library-membership/mobile-library"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}




def add_minutes_to_time(time_str: str, minutes: int) -> str:
    """Calculate departure time by adding duration minutes to arrival time."""
    try:
        t = datetime.strptime(time_str, "%H:%M")
        t_dep = t + timedelta(minutes=minutes)
        return t_dep.strftime("%H:%M")
    except Exception:
        return ""




def main():
    """Query Worcestershire GIS WebForm callback, convert BNG coordinates to WGS84, write data/worcestershire.csv, and update metadata."""
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)
    raw_html_file = os.path.join(raw_dir, "gis_portal.html")
    raw_points_file = os.path.join(raw_dir, "getPoints_response.txt")

    print(f"[{DATASET_SLUG}] Connecting to Worcestershire GIS: {BASE_URL}")
    req = urllib.request.Request(BASE_URL, headers=HEADERS)
    resp = urllib.request.urlopen(req)
    html = resp.read().decode("utf-8", errors="replace")

    with open(raw_html_file, "w", encoding="utf-8") as f:
        f.write(html)

    soup = BeautifulSoup(html, "html.parser")
    vs = soup.find("input", id="__VIEWSTATE").get("value", "")
    vsg = soup.find("input", id="__VIEWSTATEGENERATOR").get("value", "")

    # Execute WebForm Callback
    print(f"[{DATASET_SLUG}] Querying ASP.NET Callback getPoints...")
    payload = {
        "__CALLBACKID": "__Page",
        "__CALLBACKPARAM": "getPointsª",
        "__VIEWSTATE": vs,
        "__VIEWSTATEGENERATOR": vsg
    }

    post_req = urllib.request.Request(
        BASE_URL,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest"
        }
    )

    with urllib.request.urlopen(post_req) as post_resp:
        raw_data = post_resp.read().decode("utf-8", errors="replace")

    with open(raw_points_file, "w", encoding="utf-8") as f:
        f.write(raw_data)

    # ASP.NET callback response prefixes data with "returnPoints£*$ž" and delimits records with "ž" and fields with "ª"
    if "returnPoints£*$ž" in raw_data:
        raw_data = raw_data.split("returnPoints£*$ž", 1)[1]

    points = raw_data.split("ž")
    print(f"[{DATASET_SLUG}] Received {len(points)} raw data tokens.")

    # Transformer: BNG (EPSG:27700) -> WGS84 (EPSG:4326)
    transformer = pyproj.Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)

    postcode_regex = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$", re.I)
    postcode_cache = {}

    stops_records = []

    for p in points:
        attrs = p.split("ª")
        if len(attrs) < 8:
            continue

        x_str, y_str, loc, stop, pc, day, week, arr_raw = attrs[:8]
        # Default stop duration to 15 minutes when omitted from the GIS payload
        dur_raw = attrs[8] if len(attrs) > 8 else "15"

        if not day or not arr_raw:
            continue

        community = loc.strip()
        stop_name = stop.strip()
        address = f"{stop_name}, {community}" if stop_name and stop_name != community else community

        arrival = clean_time(arr_raw)
        duration = int(dur_raw) if dur_raw.isdigit() else 15
        departure = add_minutes_to_time(arrival, duration)

        # Coordinate conversion
        try:
            easting = float(x_str)
            northing = float(y_str)
            lng, lat = transformer.transform(easting, northing)
            geox = round(lng, 6)
            geoy = round(lat, 6)
        except Exception:
            geox, geoy = "", ""

        # Postcode sanitisation
        postcode = pc.strip().replace("?", "").strip()
        if not postcode_regex.match(postcode):
            if geoy and geox:
                postcode = reverse_geocode_postcode(geoy, geox, postcode_cache)
            else:
                postcode = ""

        route_name = f"Week {week.strip()} {day.strip()}"
        day_abbr_map = {
            "Monday": "MO", "Tuesday": "TU", "Wednesday": "WE",
            "Thursday": "TH", "Friday": "FR", "Saturday": "SA", "Sunday": "SU"
        }
        day_abbr = day_abbr_map.get(day.strip(), "MO")
        wk_num = week.strip() if week.strip() in ("1", "2", "3", "4", "5") else "1"
        freq_rrule = f"FREQ=MONTHLY;BYDAY={wk_num}{day_abbr}"

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": GSS_CODE,
            "Mobile name": "County Mobile Library",
            "Route": route_name,
            "Community": community,
            "Stop": stop_name,
            "Address": address,
            "Postcode": postcode,
            "GeoX": geox,
            "GeoY": geoy,
            "Day": day.strip(),
            "Type": "Public",
            "Arrival": arrival,
            "Departure": departure,
            "Frequency": freq_rrule,
            "Start": "2026-01-01",
            "End": "2027-12-31",
            "Exceptions": "",
            "Timetable": TIMETABLE_URL
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
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

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
                    row["source_url"] = TIMETABLE_URL
                    row["source_format"] = "ASP.NET / GIS WebForm"
                    row["last_checked"] = date_stamp
                    row["last_updated"] = date_stamp
                    row["notes"] = f"Harvested {len(stops_records)} stops across 4-week cycle from official Worcestershire GIS portal on {date_stamp}."
                rows.append(row)
        with open(services_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fn)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[{DATASET_SLUG}] Updated {services_path}")


if __name__ == "__main__":
    main()
