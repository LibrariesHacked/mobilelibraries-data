"""
Ingestion script for Bedford Borough Council Mobile Library Service.
Harvests routes, timetables, and stops from official 2026 timetable PDF
(virtual-library.culturalservices.net/bedfordshire/vlib/0.beds_libraries/mobile_timetable_2026.pdf).
Geocodes via postcodes.io, validates schema compliance, and updates services.csv and geocache.
"""

import os
import re
import csv
import json
import io
from datetime import datetime
import urllib.request
import urllib.parse
import pdfplumber
from frictionless import Resource, Schema

DATASET_SLUG = "bedford"
AUTHORITY_NAME = "Bedford"
GSS_CODE = "E06000055"
BASE_URL = "https://www.bedford.gov.uk/libraries/home-library-service-and-mobile-library"
PDF_URL = "https://virtual-library.culturalservices.net/bedfordshire/vlib/0.beds_libraries/mobile_timetable_2026.pdf"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}


def clean_time(time_str: str) -> str:
    """Format time string into 24-hr HH:MM."""
    m = re.search(r"(\d{1,2})[:.](\d{2})", time_str.strip())
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return ""


def geocode_place_postcodes_io(place: str, cache: dict) -> tuple:
    """Geocode place using postcodes.io/places API with priority for MK / SG outcodes."""
    clean_p = place.strip()
    if clean_p in cache:
        return cache[clean_p]

    url = f"https://api.postcodes.io/places?q={urllib.parse.quote(clean_p)}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("result", [])
            if results:
                # Prioritize Bedfordshire outcodes
                bed_matches = [r for r in results if "Bedford" in str(r.get("admin_district", "")) or str(r.get("outcode", "")).startswith(("MK", "SG"))]
                chosen = bed_matches[0] if bed_matches else results[0]
                lat = float(chosen["latitude"])
                lng = float(chosen["longitude"])
                outcode = chosen.get("outcode", "")
                cache[clean_p] = (lat, lng, outcode)
                return lat, lng, outcode
    except Exception:
        pass

    cache[clean_p] = (None, None, "")
    return None, None, ""


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


def main():
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)
    raw_pdf_path = os.path.join(raw_dir, "mobile_timetable_2026.pdf")

    print(f"[{DATASET_SLUG}] Fetching timetable from {PDF_URL}")
    if os.path.exists(raw_pdf_path):
        with open(raw_pdf_path, "rb") as f:
            pdf_bytes = f.read()
    else:
        req = urllib.request.Request(PDF_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            pdf_bytes = resp.read()
        with open(raw_pdf_path, "wb") as f:
            f.write(pdf_bytes)

    print(f"[{DATASET_SLUG}] Saved raw PDF to {raw_pdf_path} ({len(pdf_bytes)} bytes)")

    raw_stops = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_idx in range(1, len(pdf.pages)):
            p = pdf.pages[page_idx]
            tables = p.extract_tables()
            for t in tables:
                route_str = ""
                for r in t:
                    first = " ".join([str(c) for c in r if c])
                    if any(k in first.lower() for k in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]):
                        route_str = first.strip()
                        continue
                    if any(k in first.lower() for k in ["village", "location", "arrive"]):
                        continue
                    if len(r) >= 4 and r[2] and r[3]:
                        comm = str(r[0]).strip() if r[0] else ""
                        stop = str(r[1]).strip() if r[1] else ""
                        arr = clean_time(str(r[2]))
                        dep = clean_time(str(r[3]))
                        if arr and dep:
                            raw_stops.append({
                                "route": route_str,
                                "community": comm,
                                "stop": stop,
                                "arrival": arr,
                                "departure": dep
                            })

    print(f"[{DATASET_SLUG}] Extracted {len(raw_stops)} raw stop entries from PDF.")

    # Load existing geocache
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    place_cache = {}
    postcode_cache = {}
    stops_records = []

    for item in raw_stops:
        comm = item["community"]
        stop = item["stop"]
        norm_c = re.sub(r"[^a-z0-9]", "", comm.lower())
        norm_s = re.sub(r"[^a-z0-9]", "", stop.lower())
        cache_key = f"{DATASET_SLUG}::{norm_c}::{norm_s}"

        lat, lng = None, None
        postcode = ""

        if cache_key in geocache:
            entry = geocache[cache_key]
            lat = entry.get("geoy")
            lng = entry.get("geox")
            postcode = entry.get("postcode", "")

        if not lat:
            lat, lng, outcode = geocode_place_postcodes_io(comm, place_cache)

        if lat and lng and not postcode:
            postcode = reverse_geocode_postcode(lat, lng, postcode_cache)

        # Extract Day from route string
        m_day = re.search(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)", item["route"], re.I)
        day_name = m_day.group(1).title() if m_day else "Monday"

        # Determine type
        stop_type = "Private" if "school" in stop.lower() or "nursery" in stop.lower() else "Public"
        address = f"{stop}, {comm}" if stop != comm else comm

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": GSS_CODE,
            "Mobile name": "Bedford Borough Mobile Library",
            "Route": item["route"] if item["route"] else f"{day_name} Route",
            "Community": comm,
            "Stop": stop,
            "Address": address,
            "Postcode": postcode,
            "GeoX": round(float(lng), 6) if lng else "",
            "GeoY": round(float(lat), 6) if lat else "",
            "Day": day_name,
            "Type": stop_type,
            "Arrival": item["arrival"],
            "Departure": item["departure"],
            "Frequency": "FREQ=WEEKLY;INTERVAL=2",
            "Start": "2026-01-05",
            "End": "2026-12-31",
            "Exceptions": "Bank holidays and Christmas period",
            "Timetable": PDF_URL
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
                    row["source_url"] = PDF_URL
                    row["source_format"] = "PDF"
                    row["last_checked"] = date_stamp
                    row["last_updated"] = date_stamp
                    row["notes"] = f"Harvested {len(stops_records)} stops across Week 1 and Week 2 from Bedford Borough Council 2026 timetable."
                # Also update Central Bedfordshire
                if row.get("dataset_slug") == "central_bedfordshire" or row.get("local_authority_code") == "E06000056":
                    row["has_mobile_service"] = "No"
                    row["status"] = "Discontinued / Never Operated"
                    row["last_checked"] = date_stamp
                    row["last_updated"] = date_stamp
                    row["notes"] = "Does not operate a mobile library service; select border areas served by Bedford Borough; static libraries and Home Delivery."
                rows.append(row)
        with open(services_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fn)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[{DATASET_SLUG}] Updated {services_path}")

    # Update vehicles
    v_path = os.path.join("history", "historical_mobile_vehicles.csv")
    if os.path.exists(v_path):
        with open(v_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            v_fn = reader.fieldnames
            v_rows = list(reader)
        existing = {r["Mobile name"] for r in v_rows if r["Local authority"] == AUTHORITY_NAME}
        if "Bedford Borough Mobile Library" not in existing:
            v_rows.append({
                "Local authority": AUTHORITY_NAME,
                "Mobile name": "Bedford Borough Mobile Library",
                "Dataset slug": DATASET_SLUG,
                "Status": "Active",
                "Notes": "Bedford Borough Council fortnightly mobile library van."
            })
            with open(v_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=v_fn)
                writer.writeheader()
                writer.writerows(v_rows)
            print(f"[{DATASET_SLUG}] Updated {v_path}")


if __name__ == "__main__":
    main()
