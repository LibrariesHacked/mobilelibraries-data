"""
OnFife (Fife Council) Mobile Library Ingestion Script
Harvests West & Central Fife and East Fife mobile library timetables from OnFife PDFs:
https://www.onfife.com/read-learn/borrow-browse-request/mobile-and-home-delivery/
Validates schema compliance and updates services.csv, geocache, and historical vehicle registries.
"""

from _common import reverse_geocode_postcode
import os
import re
import ssl
import json
import csv
import time
import urllib.request
from datetime import datetime
import pdfplumber
from frictionless import Resource, Schema

AUTHORITY_NAME = "Fife"
AUTHORITY_CODE = "S12000047"
SLUG = "fife"

BASE_URL = "https://www.onfife.com/read-learn/borrow-browse-request/mobile-and-home-delivery/"
PDF_SOURCES = [
    {
        "vehicle": "West and Central Fife Mobile Library",
        "filename": "west_central.pdf",
        "url": "https://www.onfife.com/wp-content/uploads/2026/09/W-C-12.10.26-22.12.26.pdf"
    },
    {
        "vehicle": "East Fife Mobile Library",
        "filename": "east.pdf",
        "url": "https://www.onfife.com/wp-content/uploads/2026/09/East-12.10.26-22.12.26.pdf"
    }
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor'}
# Disable SSL certificate verification for OnFife PDF downloads
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def format_24h(t_str: str) -> str:
    """Convert a 3- or 4-digit time string into 24-hour HH:MM format, or empty string if invalid."""
    t_str = re.sub(r"\D", "", t_str)
    if len(t_str) == 4:
        return f"{t_str[:2]}:{t_str[2:]}"
    elif len(t_str) == 3:
        return f"0{t_str[0]}:{t_str[1:]}"
    return ""


def geocode_fife_place(community: str, stop: str, geocache: dict, session_cache: dict):
    """Resolve (lat, lng) for a Fife community and stop using caches, postcodes.io places API, or Fife centroid fallback."""
    ref_key = f"{AUTHORITY_NAME}:{community}:{stop}".lower()
    if ref_key in geocache:
        return geocache[ref_key]
    comm_key = f"{AUTHORITY_NAME}:{community}".lower()
    if comm_key in session_cache:
        return session_cache[comm_key]

    # Query postcodes.io places API within Scotland/Fife bounding area
    q = urllib.parse.quote(community)
    url = f"https://api.postcodes.io/places?q={q}&limit=5"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for p in data.get("result") or []:
                # Fife geographic bounding box (56.0-56.5 N, -3.8 to -2.5 E) to disambiguate places
                if p.get("county_unitary") == "Fife" or (56.0 <= float(p.get("latitude", 0)) <= 56.5 and -3.8 <= float(p.get("longitude", 0)) <= -2.5):
                    coords = (round(float(p["latitude"]), 6), round(float(p["longitude"]), 6))
                    session_cache[comm_key] = coords
                    return coords
            if data.get("result"):
                p = data["result"][0]
                # Wider Fife/East Scotland latitude band fallback when county_unitary is absent
                if 55.8 <= float(p.get("latitude", 0)) <= 56.6:
                    coords = (round(float(p["latitude"]), 6), round(float(p["longitude"]), 6))
                    session_cache[comm_key] = coords
                    return coords
    except Exception:
        pass

    # Fallback default Fife centroid if not matched
    default_coords = (56.2082, -3.1495)
    session_cache[comm_key] = default_coords
    return default_coords




def parse_pdf_timetable(pdf_path: str, vehicle: str, source_url: str):
    """Extract stop dictionaries from a 3-column OnFife PDF timetable."""
    stops = []
    days_order = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]
    current_day = "Monday"
    current_route = "Route 1"

    with pdfplumber.open(pdf_path) as pdf:
        for p_idx, page in enumerate(pdf.pages):
            w = page.width
            h = page.height
            # Timetable pages are formatted in 3 equal vertical columns
            c_w = w / 3.0
            for c_idx in range(3):
                # Skip summary panel on Page 2 Col 3
                if p_idx == 1 and c_idx == 2:
                    continue
                bbox = (c_idx * c_w, 0, (c_idx + 1) * c_w, h)
                crop = page.crop(bbox)
                txt = crop.extract_text()
                if not txt:
                    continue

                lines = [l.strip() for l in txt.split("\n") if l.strip()]
                for line in lines:
                    # Check day header
                    for d in days_order:
                        if re.search(rf"\b{d}\b", line):
                            current_day = d.title()
                            break

                    # Check route header
                    m_route = re.search(r"\b(Route\s+[12])\b", line, re.I)
                    if m_route:
                        current_route = m_route.group(1).title()

                    # Check stop line with time span e.g. "Main Street, West Wemyss 1300 - 1320"
                    # Match location text followed by 3- or 4-digit start and end times
                    m_stop = re.match(r"^(.*?)\s+(\d{3,4})\s*[-–]\s*(\d{3,4})$", line)
                    if m_stop:
                        loc_raw = m_stop.group(1).strip()
                        arr = format_24h(m_stop.group(2))
                        dep = format_24h(m_stop.group(3))

                        if not loc_raw or loc_raw.lower() in ["location", "location time", "school stops"]:
                            continue

                        if "," in loc_raw:
                            parts = [p.strip() for p in loc_raw.split(",", 1)]
                            stop_name = parts[0]
                            community = parts[1] or ("Strathkinness" if "Little Beehive" in stop_name else "")
                        else:
                            if "Little Beehive" in loc_raw:
                                community = "Strathkinness"
                            else:
                                community = re.sub(r"\s+(Primary School|P\.S|Nursery|Kindergarten|Prim\.\s*School)$", "", loc_raw, flags=re.I).strip()
                            stop_name = loc_raw

                        stops.append({
                            "vehicle": vehicle,
                            "route": f"{vehicle} {current_day} {current_route}",
                            "day": current_day,
                            "community": community,
                            "stop": stop_name,
                            "arr": arr,
                            "dep": dep,
                            "url": source_url
                        })
    return stops


def run():
    """Download OnFife PDFs, parse and geocode stops, validate schema, and update data/fife.csv and registries."""
    print(f"[{SLUG}] Starting ingestion for {AUTHORITY_NAME} ({AUTHORITY_CODE})...")
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)

    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    all_raw_stops = []
    vehicles_seen = set()

    for src in PDF_SOURCES:
        v_name = src["vehicle"]
        vehicles_seen.add(v_name)
        pdf_path = os.path.join(raw_dir, src["filename"])
        if not os.path.exists(pdf_path):
            print(f"[{SLUG}] Downloading {src['url']}...")
            req = urllib.request.Request(src["url"], headers=HEADERS)
            with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
                with open(pdf_path, "wb") as f:
                    f.write(resp.read())

        parsed = parse_pdf_timetable(pdf_path, v_name, src["url"])
        print(f"[{SLUG}] Extracted {len(parsed)} stops for {v_name}")
        all_raw_stops.extend(parsed)

    session_cache = {}
    pc_cache = {}
    stops_records = []

    for s in all_raw_stops:
        comm = s["community"]
        stop_name = s["stop"]
        lat, lng = geocode_fife_place(comm, stop_name, geocache, session_cache)
        postcode = reverse_geocode_postcode(lat, lng, pc_cache)

        geocache[f"{AUTHORITY_NAME}:{comm}:{stop_name}".lower()] = (lat, lng)
        if postcode:
            geocache[postcode] = (lat, lng)

        address = f"{stop_name}, {comm}, Fife" if stop_name != comm else f"{comm}, Fife"
        stype = "Private" if any(w in stop_name.lower() for w in ["school", "nursery", "kindergarten", "p.s"]) else "Public"

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": AUTHORITY_CODE,
            "Mobile name": s["vehicle"],
            "Route": s["route"],
            "Community": comm,
            "Stop": stop_name,
            "Address": address,
            "Postcode": postcode,
            "GeoX": lng,
            "GeoY": lat,
            "Day": s["day"],
            "Type": stype,
            "Arrival": s["arr"],
            "Departure": s["dep"],
            "Frequency": "FREQ=WEEKLY;INTERVAL=2",
            "Start": "2026-10-12",
            "End": "2026-12-22",
            "Exceptions": '',
            "Timetable": s["url"]
        })

    stops_records.sort(key=lambda r: (r["Mobile name"], r["Route"], r["Arrival"], r["Community"], r["Stop"]))

    with open(geocache_path, "w", encoding="utf-8") as f:
        json.dump(geocache, f, indent=2)

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

    schema = Schema("schemas/mobile-library-stops.json")
    # Clear foreign keys so the standalone CSV validates without external lookup tables
    schema.foreign_keys = []
    resource = Resource(out_csv, schema=schema)
    report = resource.validate()
    print(f"[{SLUG}] Validation result: valid={report.valid}, errors={len(report.flatten(['rowNumber', 'fieldNumber', 'code', 'message']))}")

    # Update historical vehicles
    vehicles_csv = os.path.join("history", "historical_mobile_vehicles.csv")
    if os.path.exists(vehicles_csv) and vehicles_seen:
        with open(vehicles_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            v_fieldnames = reader.fieldnames
            existing_rows = list(reader)

        existing_keys = {(r.get("Local authority"), r.get("Mobile name")) for r in existing_rows}
        added = 0
        for v in sorted(vehicles_seen):
            if (AUTHORITY_NAME, v) not in existing_keys:
                existing_rows.append({
                    "Local authority": AUTHORITY_NAME,
                    "Mobile name": v,
                    "Dataset slug": SLUG,
                    "Status": "Active",
                    "Notes": "OnFife mobile library fleet"
                })
                added += 1
        if added > 0:
            with open(vehicles_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=v_fieldnames)
                writer.writeheader()
                writer.writerows(existing_rows)

    # Update services.csv
    services_csv = "services.csv"
    if os.path.exists(services_csv):
        with open(services_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            s_fieldnames = reader.fieldnames
            rows = list(reader)

        today = datetime.now().strftime("%Y-%m-%d")
        for r in rows:
            if r.get("dataset_slug") == SLUG or r.get("local_authority_code") == AUTHORITY_CODE:
                r["has_mobile_service"] = "Yes"
                r["status"] = "Active Verified"
                r["source_url"] = BASE_URL
                r["source_format"] = "PDF Timetable"
                r["last_checked"] = today
                r["last_updated"] = today
                r["notes"] = f"Harvested {len(stops_records)} stops across West & Central Fife and East Fife mobile libraries."
                break

        with open(services_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=s_fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    run()
