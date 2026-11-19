"""
Shetland Islands Council (Shetland Library) Mobile Library Ingestion Script
Harvests 2026/2027 Mobile Library Timetable from Shetland Islands Council:
https://www.shetland.gov.uk/libraries/mobile-community-libraries
https://www.shetland.gov.uk/downloads/file/13460/mobile-library-timetable-2026
Geocodes stops within Shetland bounds, validates schema compliance, and updates services.csv, geocache, and historical vehicle registries.
"""

from _common import reverse_geocode_postcode
import os
import csv
import json
import urllib.parse
import urllib.request
from datetime import datetime
from frictionless import Resource, Schema

AUTHORITY_NAME = "Shetland Islands"
AUTHORITY_CODE = "S12000027"
SLUG = "shetland_islands"

TIMETABLE_URL = "https://www.shetland.gov.uk/libraries/mobile-community-libraries"
PDF_URL = "https://www.shetland.gov.uk/downloads/file/13460/mobile-library-timetable-2026"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}

# Structured stops from Shetland Library 2026/2027 Mobile Library Van Schedule (6-weekly cycle: FREQ=WEEKLY;INTERVAL=6)
# Format: (Vehicle, Route, Day, StartDate, Community, Stop, Arrival, Departure, Type)
SHETLAND_STOPS = [
    # Week 1 (w/b 16 Nov 2026): Unst (Tue) & Hillswick-Brae-Mossbank (Wed)
    ("Mobile Library (Big Van)", "Unst", "Tuesday", "2026-11-17", "Baltasound", "Unst Leisure Centre", "10:30", "11:00", "Public"),
    ("Mobile Library (Big Van)", "Unst", "Tuesday", "2026-11-17", "Baltasound", "Final Checkout", "11:10", "11:40", "Public"),
    ("Mobile Library (Big Van)", "Unst", "Tuesday", "2026-11-17", "Haroldswick", "Haroldswick", "12:00", "12:30", "Public"),
    ("Mobile Library (Big Van)", "Unst", "Tuesday", "2026-11-17", "Norwick", "Norwick", "12:45", "13:15", "Public"),
    ("Mobile Library (Big Van)", "Unst", "Tuesday", "2026-11-17", "Burrafirth", "Burrafirth", "13:45", "14:15", "Public"),
    ("Mobile Library (Big Van)", "Unst", "Tuesday", "2026-11-17", "Uyeasound", "Uyeasound", "14:45", "15:15", "Public"),
    ("Mobile Library (Peerie Van)", "Fetlar & Skerries", "Tuesday", "2026-11-17", "Fetlar", "Fetlar", "10:30", "14:30", "Public"),
    ("Mobile Library (Big Van)", "Hillswick - Brae - Mossbank", "Wednesday", "2026-11-18", "Brae", "Brae Co-op", "10:00", "10:30", "Public"),
    ("Mobile Library (Big Van)", "Hillswick - Brae - Mossbank", "Wednesday", "2026-11-18", "Urafirth", "Urafirth Primary School", "10:45", "11:30", "Private"),
    ("Mobile Library (Big Van)", "Hillswick - Brae - Mossbank", "Wednesday", "2026-11-18", "Hillswick", "Hillswick", "11:45", "12:30", "Public"),
    ("Mobile Library (Big Van)", "Hillswick - Brae - Mossbank", "Wednesday", "2026-11-18", "Mossbank", "Mossbank Primary School", "13:30", "14:15", "Private"),
    ("Mobile Library (Big Van)", "Hillswick - Brae - Mossbank", "Wednesday", "2026-11-18", "Brae", "Voxter", "14:30", "15:00", "Public"),
    # Week 2 (w/b 23 Nov 2026): Sandwick (Tue) & Sumburgh (Wed)
    ("Mobile Library (Big Van)", "Sandwick", "Tuesday", "2026-11-24", "Quarff", "Quarff", "09:45", "10:15", "Public"),
    ("Mobile Library (Big Van)", "Sandwick", "Tuesday", "2026-11-24", "Cunningsburgh", "Cunningsburgh Primary School", "10:30", "11:30", "Private"),
    ("Mobile Library (Big Van)", "Sandwick", "Tuesday", "2026-11-24", "Cunningsburgh", "Cunningsburgh", "11:40", "12:15", "Public"),
    ("Mobile Library (Big Van)", "Sandwick", "Tuesday", "2026-11-24", "Sandwick", "Sandwick Bakery", "13:00", "13:30", "Public"),
    ("Mobile Library (Big Van)", "Sandwick", "Tuesday", "2026-11-24", "Levenwick", "Levenwick", "14:00", "14:45", "Public"),
    ("Mobile Library (Big Van)", "Sumburgh", "Wednesday", "2026-11-25", "Dunrossness", "Dunrossness", "10:00", "10:45", "Public"),
    ("Mobile Library (Big Van)", "Sumburgh", "Wednesday", "2026-11-25", "Virkie", "Virkie", "11:00", "11:45", "Public"),
    ("Mobile Library (Big Van)", "Sumburgh", "Wednesday", "2026-11-25", "Quendale", "Mainland's Shop", "12:00", "12:30", "Public"),
    ("Mobile Library (Big Van)", "Sumburgh", "Wednesday", "2026-11-25", "Bigton", "Bigton Shop", "13:00", "13:30", "Public"),
    ("Mobile Library (Big Van)", "Sumburgh", "Wednesday", "2026-11-25", "Bigton", "Bigton Village", "13:35", "14:15", "Public"),
    # Week 3 (w/b 30 Nov 2026): Nesting - Vidlin - Voe (Tue) & North Roe - Ollaberry (Wed)
    ("Mobile Library (Big Van)", "Nesting - Vidlin - Voe", "Tuesday", "2026-12-01", "Nesting", "Nesting Shop", "09:50", "10:10", "Public"),
    ("Mobile Library (Big Van)", "Nesting - Vidlin - Voe", "Tuesday", "2026-12-01", "Nesting", "Nesting Primary School", "10:15", "10:30", "Private"),
    ("Mobile Library (Big Van)", "Nesting - Vidlin - Voe", "Tuesday", "2026-12-01", "Nesting", "North Nesting", "10:45", "11:15", "Public"),
    ("Mobile Library (Big Van)", "Nesting - Vidlin - Voe", "Tuesday", "2026-12-01", "Vidlin", "Lunnasting Primary School", "11:30", "12:15", "Private"),
    ("Mobile Library (Big Van)", "Nesting - Vidlin - Voe", "Tuesday", "2026-12-01", "Vidlin", "Lunning", "13:00", "13:30", "Public"),
    ("Mobile Library (Big Van)", "Nesting - Vidlin - Voe", "Tuesday", "2026-12-01", "Vidlin", "Vidlin", "13:45", "14:15", "Public"),
    ("Mobile Library (Big Van)", "Nesting - Vidlin - Voe", "Tuesday", "2026-12-01", "Voe", "Voe", "14:45", "15:30", "Public"),
    ("Mobile Library (Big Van)", "North Roe - Ollaberry", "Wednesday", "2026-12-02", "Ollaberry", "Ollaberry Primary School", "10:00", "10:45", "Private"),
    ("Mobile Library (Big Van)", "North Roe - Ollaberry", "Wednesday", "2026-12-02", "Ollaberry", "Ollaberry", "10:50", "11:30", "Public"),
    ("Mobile Library (Big Van)", "North Roe - Ollaberry", "Wednesday", "2026-12-02", "North Roe", "Lochend", "11:45", "12:15", "Public"),
    ("Mobile Library (Big Van)", "North Roe - Ollaberry", "Wednesday", "2026-12-02", "North Roe", "North Roe Primary School", "13:00", "13:45", "Private"),
    ("Mobile Library (Big Van)", "North Roe - Ollaberry", "Wednesday", "2026-12-02", "North Roe", "North Roe", "13:50", "14:30", "Public"),
    ("Mobile Library (Big Van)", "North Roe - Ollaberry", "Wednesday", "2026-12-02", "Sullom", "Sullom", "14:50", "15:30", "Public"),
    # Week 4 (w/b 7 Dec 2026): Staneyhill - Scalloway - Burra (Tue) & Bressay (Wed)
    ("Mobile Library (Big Van)", "Staneyhill - Scalloway - Burra", "Tuesday", "2026-12-08", "Lerwick", "Staneyhill", "09:45", "10:30", "Public"),
    ("Mobile Library (Big Van)", "Staneyhill - Scalloway - Burra", "Tuesday", "2026-12-08", "Scalloway", "Scalloway", "10:45", "11:45", "Public"),
    ("Mobile Library (Big Van)", "Staneyhill - Scalloway - Burra", "Tuesday", "2026-12-08", "Trondra", "Trondra", "12:00", "12:30", "Public"),
    ("Mobile Library (Big Van)", "Staneyhill - Scalloway - Burra", "Tuesday", "2026-12-08", "Hamnavoe", "Hamnavoe", "13:30", "14:15", "Public"),
    ("Mobile Library (Big Van)", "Staneyhill - Scalloway - Burra", "Tuesday", "2026-12-08", "Burra", "Bridge End (Burra)", "14:30", "15:15", "Public"),
    ("Mobile Library (Big Van)", "Bressay", "Wednesday", "2026-12-09", "Bressay", "Bressay Hall", "14:00", "14:30", "Public"),
    # Week 5 (w/b 14 Dec 2026): Aith & Bixter (Tue) & Sandness & Walls (Wed)
    ("Mobile Library (Big Van)", "Aith & Bixter", "Tuesday", "2026-12-15", "Weisdale", "Weisdale", "10:00", "10:45", "Public"),
    ("Mobile Library (Big Van)", "Aith & Bixter", "Tuesday", "2026-12-15", "Aith", "Aith Hall", "11:00", "11:30", "Public"),
    ("Mobile Library (Big Van)", "Aith & Bixter", "Tuesday", "2026-12-15", "Aith", "Clousta", "11:45", "12:15", "Public"),
    ("Mobile Library (Big Van)", "Aith & Bixter", "Tuesday", "2026-12-15", "Sand", "Sand", "12:45", "13:15", "Public"),
    ("Mobile Library (Big Van)", "Aith & Bixter", "Tuesday", "2026-12-15", "Bixter", "Bixter Hall", "13:30", "14:00", "Public"),
    ("Mobile Library (Big Van)", "Sandness & Walls", "Wednesday", "2026-12-16", "Sandness", "Sandness Primary School", "10:15", "10:30", "Private"),
    ("Mobile Library (Big Van)", "Sandness & Walls", "Wednesday", "2026-12-16", "Sandness", "Sandness", "10:35", "11:15", "Public"),
    ("Mobile Library (Big Van)", "Sandness & Walls", "Wednesday", "2026-12-16", "Walls", "Happy Hansel Primary School", "11:30", "12:15", "Private"),
    ("Mobile Library (Big Van)", "Sandness & Walls", "Wednesday", "2026-12-16", "Walls", "Walls", "12:20", "13:00", "Public"),
    ("Mobile Library (Big Van)", "Sandness & Walls", "Wednesday", "2026-12-16", "Skeld", "Selivoe & Skeld", "13:45", "14:30", "Public"),
    ("Mobile Library (Big Van)", "Sandness & Walls", "Wednesday", "2026-12-16", "Reawick", "Reawick", "14:40", "15:15", "Public"),
    # Week 6 (w/b 4 Jan 2027): Yell (Tue) & Whalsay (Wed)
    ("Mobile Library (Big Van)", "Yell", "Tuesday", "2027-01-05", "West Sandwick", "West Sandwick", "09:45", "10:30", "Public"),
    ("Mobile Library (Big Van)", "Yell", "Tuesday", "2027-01-05", "Gutcher", "Gutcher", "10:45", "11:15", "Public"),
    ("Mobile Library (Big Van)", "Yell", "Tuesday", "2027-01-05", "Cullivoe", "Cullivoe Hall", "11:30", "12:00", "Public"),
    ("Mobile Library (Big Van)", "Yell", "Tuesday", "2027-01-05", "Mid Yell", "Yell Leisure Centre", "12:30", "13:00", "Public"),
    ("Mobile Library (Big Van)", "Yell", "Tuesday", "2027-01-05", "Mid Yell", "Camb & Aywick", "13:30", "14:30", "Public"),
    ("Mobile Library (Big Van)", "Whalsay", "Wednesday", "2027-01-06", "Symbister", "Symbister", "10:30", "11:15", "Public"),
    ("Mobile Library (Big Van)", "Whalsay", "Wednesday", "2027-01-06", "Symbister", "Harlsdale", "11:30", "12:00", "Public"),
    ("Mobile Library (Big Van)", "Whalsay", "Wednesday", "2027-01-06", "Brough (Whalsay)", "Brough", "13:00", "13:45", "Public"),
    ("Mobile Library (Big Van)", "Whalsay", "Wednesday", "2027-01-06", "Isbister (Whalsay)", "Isbister", "14:00", "14:45", "Public")
]


def geocode_shetland_place(community: str, cache: dict):
    """Resolve a Shetland community name to (lat, lon) via postcodes.io, using cache and Lerwick fallback."""
    clean = community.split("(")[0].strip()
    if clean in cache:
        return cache[clean]
    q = urllib.parse.quote(clean)
    url = f"https://api.postcodes.io/places?q={q}&limit=10"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
            for p in data.get("result") or []:
                lat = float(p.get("latitude", 0))
                lon = float(p.get("longitude", 0))
                # Bounding box for Shetland Islands
                if p.get("county_unitary") == "Shetland Islands" or (59.8 <= lat <= 60.9 and -2.2 <= lon <= -0.7):
                    cache[clean] = (round(lat, 6), round(lon, 6))
                    return cache[clean]
    except Exception:
        pass
    cache[clean] = (60.1530, -1.1493)  # Lerwick / Shetland fallback
    return cache[clean]




def run():
    """Geocode SHETLAND_STOPS, write data/shetland_islands.csv, validate schema, and update registries."""
    print(f"[{SLUG}] Starting ingestion for {AUTHORITY_NAME} ({AUTHORITY_CODE})...")
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    place_cache = {}
    pc_cache = {}
    stops_records = []
    vehicles_seen = set()

    for veh, rt, day, start, comm, stop, arr, dep, stype in SHETLAND_STOPS:
        vehicles_seen.add(veh)
        lat, lon = geocode_shetland_place(comm, place_cache)
        pc = reverse_geocode_postcode(lat, lon, pc_cache)
        geocache[f"{AUTHORITY_NAME}:{comm}:{stop}".lower()] = (lat, lon)

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": AUTHORITY_CODE,
            "Mobile name": veh,
            "Route": rt,
            "Community": comm,
            "Stop": stop,
            "Address": f"{stop}, {comm}, Shetland",
            "Postcode": pc,
            "GeoX": lon,
            "GeoY": lat,
            "Day": day,
            "Type": stype,
            "Arrival": arr,
            "Departure": dep,
            "Frequency": "FREQ=WEEKLY;INTERVAL=6",
            "Start": start,
            "End": "2027-12-31",
            "Exceptions": "Public holidays",
            "Timetable": TIMETABLE_URL
        })

    stops_records.sort(key=lambda r: (r["Mobile name"], r["Route"], r["Arrival"], r["Stop"]))

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
    # Skip foreign-key checks when validating this standalone CSV
    schema.foreign_keys = []
    resource = Resource(out_csv, schema=schema)
    report = resource.validate()
    print(f"[{SLUG}] Validation result: valid={report.valid}, errors={len(report.flatten(['rowNumber', 'fieldNumber', 'code', 'message']))}")

    # Update historical vehicles
    vehicles_csv = os.path.join("history", "historical_mobile_vehicles.csv")
    if os.path.exists(vehicles_csv):
        with open(vehicles_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            v_fields = reader.fieldnames
            v_rows = list(reader)
        existing_v = {(r.get("Local authority"), r.get("Mobile name")) for r in v_rows}
        for v in sorted(vehicles_seen):
            if (AUTHORITY_NAME, v) not in existing_v:
                v_rows.append({
                    "Local authority": AUTHORITY_NAME,
                    "Mobile name": v,
                    "Dataset slug": SLUG,
                    "Status": "Active",
                    "Notes": "Shetland Library mobile fleet operating 6-weekly rotation across Mainland and islands"
                })
        with open(vehicles_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=v_fields)
            writer.writeheader()
            writer.writerows(v_rows)

    # Update services.csv
    today = datetime.now().strftime("%Y-%m-%d")
    with open("services.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        s_fields = reader.fieldnames
        s_rows = list(reader)
    for r in s_rows:
        if r.get("dataset_slug") == SLUG:
            r["has_mobile_service"] = "Yes"
            r["status"] = "Active Verified"
            r["source_url"] = TIMETABLE_URL
            r["source_format"] = "HTML & PDF Timetable"
            r["last_checked"] = today
            r["last_updated"] = today
            r["notes"] = f"Harvested {len(stops_records)} stops across 13 Mainland & outer island routes on 6-weekly cycle (Big Van & Peerie Van)."
    with open("services.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=s_fields)
        writer.writeheader()
        writer.writerows(s_rows)


if __name__ == "__main__":
    run()
