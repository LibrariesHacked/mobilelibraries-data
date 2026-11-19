"""
Ingestion script for The Scottish Borders Mobile Library Service (Live Borders).
Harvests routes, timetables, and stops from official Live Borders West and East PDF timetables
(liveborders.org.uk/culture/libraries/mobile-library-service/).
Geocodes coordinates via postcodes.io/places, validates schema compliance, and updates services.csv and geocache.
"""

from _common import clean_time, parse_time_range, reverse_geocode_postcode
import os
import re
import csv
import json
import time
import io
from datetime import datetime
import urllib.request
import urllib.parse
import pdfplumber
from frictionless import Resource, Schema

DATASET_SLUG = "the_scottish_borders"
AUTHORITY_NAME = "The Scottish Borders"
GSS_CODE = "S12000026"
BASE_PAGE = "https://www.liveborders.org.uk/culture/libraries/mobile-library-service/"

PDF_SOURCES = [
    ("Mobile West (LBMB1)", "https://www.liveborders.org.uk/wp-content/uploads/2026/11/LBMB1-Timetable-Oct-26.pdf", "LBMB1_West.pdf"),
    ("Mobile East (LBMB2)", "https://www.liveborders.org.uk/wp-content/uploads/2026/11/LBMB2-Timetable-Oct-26-1.pdf", "LBMB2_East.pdf")
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}


def download_file(url: str, dest_path: str) -> bytes:
    """Return cached bytes from dest_path if present, otherwise download from url and save locally."""
    if os.path.exists(dest_path):
        with open(dest_path, "rb") as f:
            return f.read()
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read()
    with open(dest_path, "wb") as f:
        f.write(data)
    return data






def geocode_place_postcodes_io(place: str, cache: dict) -> tuple:
    """Geocode place using postcodes.io/places API with priority for TD / EH outcodes."""
    clean_p = place.replace("\n", " ").strip()
    if clean_p in cache:
        return cache[clean_p]

    url = f"https://api.postcodes.io/places?q={urllib.parse.quote(clean_p)}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("result", [])
            if results:
                # Prioritize Scottish Borders outcodes (TD, EH)
                sb_matches = [r for r in results if str(r.get("outcode", "")).upper().startswith(("TD", "EH"))]
                chosen = sb_matches[0] if sb_matches else results[0]
                lat = float(chosen["latitude"])
                lng = float(chosen["longitude"])
                outcode = chosen.get("outcode", "")
                cache[clean_p] = (lat, lng, outcode)
                return lat, lng, outcode
    except Exception:
        pass

    cache[clean_p] = (None, None, "")
    return None, None, ""




def main():
    """Download and parse the West/East PDF timetables, geocode stops, write data/the_scottish_borders.csv, and update metadata."""
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)

    # Load geocache
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    place_cache = {}
    postcode_cache = {}
    raw_stops = []

    for van_name, pdf_url, filename in PDF_SOURCES:
        dest_file = os.path.join(raw_dir, filename)
        print(f"[{DATASET_SLUG}] Downloading {van_name} timetable: {pdf_url}")
        pdf_bytes = download_file(pdf_url, dest_file)

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for t in tables:
                    current_week_day = ""
                    for row in t:
                        first = str(row[0]) if row[0] else ""
                        if "week" in first.lower():
                            current_week_day = first.strip()

                        if len(row) >= 3 and row[0] and row[1] and row[2]:
                            loc = str(row[0]).replace("\n", " ").strip()
                            stop = str(row[1]).replace("\n", " ").strip()
                            times = str(row[2]).strip()
                            if "location" not in loc.lower() and re.search(r"\d{1,2}[:.]\d{2}", times):
                                raw_stops.append({
                                    "van": van_name,
                                    "week_day": current_week_day,
                                    "location": loc,
                                    "stop": stop,
                                    "times": times,
                                    "source_pdf": pdf_url
                                })

    print(f"[{DATASET_SLUG}] Extracted {len(raw_stops)} raw stop entries from PDFs.")

    stops_records = []

    for item in raw_stops:
        loc = item["location"]
        stop = item["stop"]
        arr, dep = parse_time_range(item["times"])

        if not arr or not dep:
            continue

        week_day_str = item["week_day"]
        # Extract Day name (Monday, Tuesday, etc.)
        m_day = re.search(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)", week_day_str, re.I)
        day_name = m_day.group(1).title() if m_day else "Monday"

        norm_comm = re.sub(r"[^a-z0-9]", "", loc.lower())
        norm_stop = re.sub(r"[^a-z0-9]", "", stop.lower())
        cache_key = f"{DATASET_SLUG}::{norm_comm}::{norm_stop}"

        lat, lng = None, None
        postcode = ""

        # Check geocache first
        if cache_key in geocache:
            entry = geocache[cache_key]
            lat = entry.get("geoy")
            lng = entry.get("geox")
            postcode = entry.get("postcode", "")

        if not lat:
            lat, lng, outcode = geocode_place_postcodes_io(loc, place_cache)

        if lat and lng and not postcode:
            postcode = reverse_geocode_postcode(lat, lng, postcode_cache)

        address = f"{stop}, {loc}" if stop != loc else loc

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": GSS_CODE,
            "Mobile name": item["van"],
            "Route": week_day_str if week_day_str else f"{day_name} Route",
            "Community": loc,
            "Stop": stop,
            "Address": address,
            "Postcode": postcode,
            "GeoX": round(float(lng), 6) if lng else "",
            "GeoY": round(float(lat), 6) if lat else "",
            "Day": day_name,
            "Type": "Public",
            "Arrival": arr,
            "Departure": dep,
            "Frequency": "FREQ=WEEKLY;INTERVAL=2",
            "Start": "2026-06-29",
            "End": "2026-12-24",
            "Exceptions": "",
            "Timetable": item["source_pdf"]
        })

    print(f"[{DATASET_SLUG}] Prepared {len(stops_records)} validated stop records.")

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
    # Skip foreign-key checks when validating the stops CSV standalone
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
            norm_c = re.sub(r"[^a-z0-9]", "", s["Community"].lower())
            norm_st = re.sub(r"[^a-z0-9]", "", s["Stop"].lower())
            k1 = f"{DATASET_SLUG}::{norm_c}::{norm_st}"
            if k1 not in geocache:
                geocache[k1] = {
                    "authority": AUTHORITY_NAME,
                    "community": s["Community"],
                    "stop": s["Stop"],
                    "address": s["Address"],
                    "postcode": s["Postcode"],
                    "geox": float(s["GeoX"]),
                    "geoy": float(s["GeoY"]),
                    "source": f"{DATASET_SLUG}.csv"
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
                    row["source_url"] = BASE_PAGE
                    row["source_format"] = "PDF"
                    row["last_checked"] = date_stamp
                    row["last_updated"] = date_stamp
                    row["notes"] = f"Harvested {len(stops_records)} stops across East (LBMB2) and West (LBMB1) from Live Borders."
                rows.append(row)
        with open(services_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fn)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[{DATASET_SLUG}] Updated {services_path}")


if __name__ == "__main__":
    main()
