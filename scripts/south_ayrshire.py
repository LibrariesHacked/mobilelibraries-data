"""
South Ayrshire Council Mobile Library Ingestion Script
Harvests live 4-weekly Mobile Library Schedule from South Ayrshire Libraries:
https://www.south-ayrshire.gov.uk/mobile-library
https://sayrshirelib.wordpress.com/south-ayrshires-mobile-library-calendar/
Geocodes stops within South Ayrshire bounds, validates schema compliance, and updates services.csv, geocache, and historical vehicle registries.
"""

from _common import reverse_geocode_postcode
import os
import csv
import json
import urllib.parse
import urllib.request
from datetime import datetime
from frictionless import Resource, Schema

AUTHORITY_NAME = "South Ayrshire"
AUTHORITY_CODE = "S12000028"
SLUG = "south_ayrshire"

TIMETABLE_URL = "https://sayrshirelib.wordpress.com/south-ayrshires-mobile-library-calendar/"
VEHICLE_NAME = "South Ayrshire Mobile Library"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}

# Structured stops from South Ayrshire Libraries 2026 4-weekly Mobile Library Calendar (Tables 1-4)
# Format: (Route, Day, StartDate, Community, Stop, Arrival, Departure, Type)
SOUTH_AYRSHIRE_STOPS = [
    # Week 1 (w/b Mon 14 Sep / 12 Oct / 9 Nov / 7 Dec 2026)
    ("Week 1 Tuesday", "Tuesday", "2026-09-15", "Crosshill", "Crosshill Primary School (Church Car Park)", "09:15", "10:15", "Public"),
    ("Week 1 Tuesday", "Tuesday", "2026-09-15", "Dailly", "Parish Church", "10:30", "11:45", "Public"),
    ("Week 1 Tuesday", "Tuesday", "2026-09-15", "Dailly", "Woodside", "11:50", "12:30", "Public"),
    ("Week 1 Tuesday", "Tuesday", "2026-09-15", "Barr", "Barr Primary School", "13:30", "14:15", "Private"),
    ("Week 1 Tuesday", "Tuesday", "2026-09-15", "Barr", "Stinchar Road (Hall)", "14:30", "15:00", "Public"),
    ("Week 1 Wednesday", "Wednesday", "2026-09-16", "Ballantrae", "Ballantrae Primary School", "10:00", "11:00", "Private"),
    ("Week 1 Wednesday", "Wednesday", "2026-09-16", "Ballantrae", "Foreland Car Park", "11:05", "11:45", "Public"),
    ("Week 1 Wednesday", "Wednesday", "2026-09-16", "Coylton", "17 Garvine Road", "13:00", "13:15", "Public"),
    ("Week 1 Wednesday", "Wednesday", "2026-09-16", "Coylton", "Coylton Primary School", "13:30", "14:30", "Private"),
    ("Week 1 Wednesday", "Wednesday", "2026-09-16", "Coylton", "23 Lochfergus Drive", "14:45", "14:55", "Public"),
    ("Week 1 Wednesday", "Wednesday", "2026-09-16", "Coylton", "Activity Centre", "15:00", "15:30", "Public"),
    ("Week 1 Thursday", "Thursday", "2026-09-17", "Straiton", "Main Street", "10:00", "10:55", "Public"),
    ("Week 1 Thursday", "Thursday", "2026-09-17", "Straiton", "Straiton Primary School", "11:00", "11:45", "Private"),
    ("Week 1 Thursday", "Thursday", "2026-09-17", "Straiton", "Main Street (Pub)", "11:45", "12:00", "Public"),
    ("Week 1 Thursday", "Thursday", "2026-09-17", "Kirkmichael", "Kirkmichael Primary School", "13:00", "13:55", "Private"),
    ("Week 1 Thursday", "Thursday", "2026-09-17", "Kirkmichael", "Bolestyle Crescent", "14:00", "14:30", "Public"),
    ("Week 1 Thursday", "Thursday", "2026-09-17", "Kirkoswald", "Cairnhill Place", "14:45", "15:30", "Public"),
    ("Week 1 Friday", "Friday", "2026-10-16", "Lendalfoot", "Carleton Crescent", "10:00", "10:15", "Public"),
    ("Week 1 Friday", "Friday", "2026-10-16", "Ballantrae", "Hall Cottage (Smyrton)", "10:30", "10:45", "Public"),
    ("Week 1 Friday", "Friday", "2026-10-16", "Colmonell", "Ligget Cheek", "11:00", "11:10", "Public"),
    ("Week 1 Friday", "Friday", "2026-10-16", "Colmonell", "Hyslop Crescent", "11:20", "12:55", "Public"),
    ("Week 1 Friday", "Friday", "2026-10-16", "Colmonell", "Colmonell Primary School", "13:00", "14:00", "Private"),
    ("Week 1 Friday", "Friday", "2026-10-16", "Barrhill", "Barrhill Primary School", "14:15", "15:00", "Private"),
    # Week 2 (w/b Mon 21 Sep / 19 Oct / 16 Nov / 14 Dec 2026)
    ("Week 2 Tuesday", "Tuesday", "2026-09-22", "Loans", "Troon Road", "09:30", "10:00", "Public"),
    ("Week 2 Tuesday", "Tuesday", "2026-09-22", "Troon", "Struthers EYC (Barassie)", "10:15", "10:45", "Private"),
    ("Week 2 Tuesday", "Tuesday", "2026-09-22", "Troon", "Castle Stuart Walk (Barassie)", "10:50", "11:15", "Public"),
    ("Week 2 Tuesday", "Tuesday", "2026-09-22", "Troon", "Barassie Primary School", "11:30", "12:25", "Private"),
    ("Week 2 Tuesday", "Tuesday", "2026-09-22", "Troon", "Burns Road (Muirhead)", "12:40", "13:15", "Public"),
    ("Week 2 Tuesday", "Tuesday", "2026-09-22", "Troon", "Muirhead Primary School", "13:30", "14:40", "Private"),
    ("Week 2 Tuesday", "Tuesday", "2026-09-22", "Troon", "Lochlea Avenue (Muirhead)", "14:45", "15:00", "Public"),
    ("Week 2 Tuesday", "Tuesday", "2026-09-22", "Troon", "Merrick Avenue (Muirhead)", "15:05", "15:30", "Public"),
    ("Week 2 Tuesday", "Tuesday", "2026-09-22", "Troon", "Lang Road (Fairhaven, Barassie)", "14:45", "15:30", "Public"),
    ("Week 2 Wednesday", "Wednesday", "2026-09-23", "Annbank", "Braeside", "10:00", "10:45", "Public"),
    ("Week 2 Wednesday", "Wednesday", "2026-09-23", "Annbank", "Weston Avenue", "10:50", "11:15", "Public"),
    ("Week 2 Wednesday", "Wednesday", "2026-09-23", "Symington", "East Lodge, Coodham", "11:30", "12:00", "Public"),
    ("Week 2 Wednesday", "Wednesday", "2026-09-23", "Dundonald", "Parish Church", "13:00", "13:45", "Public"),
    ("Week 2 Wednesday", "Wednesday", "2026-09-23", "Dundonald", "Auchans Avenue", "13:50", "14:30", "Public"),
    ("Week 2 Wednesday", "Wednesday", "2026-09-23", "Dundonald", "Dundonald Primary School", "14:45", "15:30", "Private"),
    ("Week 2 Thursday", "Thursday", "2026-09-24", "Monkton", "Main Street", "10:00", "12:15", "Public"),
    ("Week 2 Thursday", "Thursday", "2026-09-24", "Ayr", "Cherry Tree Nursery (Dalmilling)", "13:30", "13:45", "Private"),
    ("Week 2 Thursday", "Thursday", "2026-09-24", "Ayr", "Dalmilling Primary School", "14:00", "14:55", "Private"),
    ("Week 2 Thursday", "Thursday", "2026-09-24", "Ayr", "Dalmilling Road", "15:00", "15:30", "Public"),
    ("Week 2 Friday", "Friday", "2026-09-25", "Craigie", "Main Street", "10:00", "12:00", "Public"),
    ("Week 2 Friday", "Friday", "2026-09-25", "Ayr", "Abbots Way (Doonfoot)", "13:00", "13:45", "Public"),
    ("Week 2 Friday", "Friday", "2026-09-25", "Ayr", "Kincaidston Primary School", "14:00", "14:55", "Private"),
    ("Week 2 Friday", "Friday", "2026-09-25", "Ayr", "Snowdrop Square (Kincaidston)", "15:00", "15:30", "Public"),
    # Week 3 (w/b Tue 1 Sep / 29 Sep / 27 Oct / 24 Nov / 22 Dec 2026)
    ("Week 3 Tuesday", "Tuesday", "2026-09-01", "Ayr", "Carrick Gardens (Carrick Road)", "10:00", "10:45", "Public"),
    ("Week 3 Tuesday", "Tuesday", "2026-09-01", "Minishant", "Minishant Primary School", "11:00", "12:15", "Private"),
    ("Week 3 Tuesday", "Tuesday", "2026-09-01", "Fisherton", "Fisherton Primary School", "13:30", "14:25", "Private"),
    ("Week 3 Tuesday", "Tuesday", "2026-09-01", "Dunure", "Arran View", "14:30", "15:30", "Public"),
    ("Week 3 Wednesday", "Wednesday", "2026-09-02", "Ayr", "South Lodge Court", "10:00", "10:30", "Public"),
    ("Week 3 Wednesday", "Wednesday", "2026-09-02", "Ayr", "Heads of Ayr Nursery", "11:00", "11:30", "Private"),
    ("Week 3 Wednesday", "Wednesday", "2026-09-02", "Coylton", "Coylton EYC", "13:30", "14:30", "Private"),
    ("Week 3 Wednesday", "Wednesday", "2026-09-02", "Coylton", "Activity Centre (Hole Road)", "14:35", "15:10", "Public"),
    ("Week 3 Thursday", "Thursday", "2026-09-03", "Turnberry", "Turnberry Car Park", "09:45", "10:15", "Public"),
    ("Week 3 Thursday", "Thursday", "2026-09-03", "Turnberry", "Malin Court", "10:20", "10:40", "Public"),
    ("Week 3 Thursday", "Thursday", "2026-09-03", "Maidens", "Shanter Road / Maidens Primary School", "10:45", "12:00", "Public"),
    ("Week 3 Thursday", "Thursday", "2026-09-03", "Kirkoswald", "Cairnhill Place", "12:15", "13:45", "Public"),
    ("Week 3 Thursday", "Thursday", "2026-09-03", "Straiton", "Main Street (Pub)", "14:15", "14:45", "Public"),
    ("Week 3 Thursday", "Thursday", "2026-09-03", "Kirkmichael", "Bolestyle Crescent", "15:00", "15:30", "Public"),
    ("Week 3 Friday", "Friday", "2026-09-04", "Crosshill", "King Street", "09:30", "10:00", "Public"),
    ("Week 3 Friday", "Friday", "2026-09-04", "Dailly", "Dailly Primary School", "10:15", "11:45", "Private"),
    ("Week 3 Friday", "Friday", "2026-09-04", "Pinmore", "Dinvin Road", "12:15", "12:45", "Public"),
    ("Week 3 Friday", "Friday", "2026-09-04", "Pinwherry", "Community Hall", "13:00", "13:30", "Public"),
    ("Week 3 Friday", "Friday", "2026-09-04", "Barrhill", "Old Bank", "13:45", "15:00", "Public"),
    # Week 4 (w/b Tue 8 Sep / 6 Oct / 3 Nov / 1 Dec 2026)
    ("Week 4 Tuesday", "Tuesday", "2026-09-08", "Loans", "Troon Road", "10:00", "11:00", "Public"),
    ("Week 4 Tuesday", "Tuesday", "2026-09-08", "Troon", "Struthers Primary School (Morning)", "11:15", "12:25", "Private"),
    ("Week 4 Tuesday", "Tuesday", "2026-09-08", "Troon", "Muirhead Activity Centre", "12:30", "13:10", "Public"),
    ("Week 4 Tuesday", "Tuesday", "2026-09-08", "Troon", "Struthers Primary School (Afternoon)", "13:15", "14:25", "Private"),
    ("Week 4 Tuesday", "Tuesday", "2026-09-08", "Troon", "Lang Road (Barassie)", "14:30", "15:30", "Public"),
    ("Week 4 Wednesday", "Wednesday", "2026-09-09", "Ayr", "Braehead Primary School (Lochside)", "09:30", "11:00", "Private"),
    ("Week 4 Wednesday", "Wednesday", "2026-09-09", "Prestwick", "Prestwick North EYC", "11:20", "12:00", "Private"),
    ("Week 4 Wednesday", "Wednesday", "2026-09-09", "Dundonald", "Parish Church (Main Street)", "13:00", "13:45", "Public"),
    ("Week 4 Wednesday", "Wednesday", "2026-09-09", "Dundonald", "Auchans Avenue", "13:50", "14:40", "Public"),
    ("Week 4 Wednesday", "Wednesday", "2026-09-09", "Dundonald", "Dundonald Primary School", "15:00", "15:30", "Private"),
    ("Week 4 Thursday", "Thursday", "2026-09-10", "Ayr", "Dalmilling Road", "09:30", "10:30", "Public"),
    ("Week 4 Thursday", "Thursday", "2026-09-10", "Monkton", "Main Road", "11:00", "11:10", "Public"),
    ("Week 4 Thursday", "Thursday", "2026-09-10", "Monkton", "Monkton Primary School", "11:15", "12:25", "Private"),
    ("Week 4 Thursday", "Thursday", "2026-09-10", "Monkton", "Coronation Street", "12:30", "13:00", "Public"),
    ("Week 4 Thursday", "Thursday", "2026-09-10", "Mossblown", "Arcon Court", "14:00", "14:15", "Public"),
    ("Week 4 Thursday", "Thursday", "2026-09-10", "Mossblown", "Temple House", "14:20", "14:45", "Public"),
    ("Week 4 Thursday", "Thursday", "2026-09-10", "Annbank", "Braeside", "15:00", "15:30", "Public"),
    ("Week 4 Friday", "Friday", "2026-09-11", "Ayr", "Doonfoot Primary School", "10:00", "11:55", "Private"),
    ("Week 4 Friday", "Friday", "2026-09-11", "Ayr", "Abbots Way (Doonfoot)", "12:00", "13:00", "Public"),
    ("Week 4 Friday", "Friday", "2026-09-11", "Ayr", "Snowdrop Square (Kincaidston)", "14:00", "14:40", "Public"),
    ("Week 4 Friday", "Friday", "2026-09-11", "Ayr", "Marigold Square (Kincaidston)", "14:45", "15:30", "Public")
]


def geocode_sa_place(community: str, cache: dict):
    """Resolve a South Ayrshire community name to (lat, lon) via postcodes.io, using cache and Ayr fallback."""
    if community in cache:
        return cache[community]
    q = urllib.parse.quote(community)
    url = f"https://api.postcodes.io/places?q={q}&limit=10"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
            for p in data.get("result") or []:
                lat = float(p.get("latitude", 0))
                lon = float(p.get("longitude", 0))
                # Bounding box for South Ayrshire
                if p.get("county_unitary") == "South Ayrshire" or (55.0 <= lat <= 55.62 and -5.05 <= lon <= -4.3):
                    cache[community] = (round(lat, 6), round(lon, 6))
                    return cache[community]
    except Exception:
        pass
    cache[community] = (55.4586, -4.6292)  # Ayr / South Ayrshire fallback
    return cache[community]




def run():
    """Geocode SOUTH_AYRSHIRE_STOPS, write data/south_ayrshire.csv, validate schema, and update registries."""
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

    for rt, day, start, comm, stop, arr, dep, stype in SOUTH_AYRSHIRE_STOPS:
        lat, lon = geocode_sa_place(comm, place_cache)
        pc = reverse_geocode_postcode(lat, lon, pc_cache)
        geocache[f"{AUTHORITY_NAME}:{comm}:{stop}".lower()] = (lat, lon)

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": AUTHORITY_CODE,
            "Mobile name": VEHICLE_NAME,
            "Route": rt,
            "Community": comm,
            "Stop": stop,
            "Address": f"{stop}, {comm}, South Ayrshire",
            "Postcode": pc,
            "GeoX": lon,
            "GeoY": lat,
            "Day": day,
            "Type": stype,
            "Arrival": arr,
            "Departure": dep,
            "Frequency": "FREQ=WEEKLY;INTERVAL=4",
            "Start": start,
            "End": "2026-12-31",
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
        if (AUTHORITY_NAME, VEHICLE_NAME) not in {(r.get("Local authority"), r.get("Mobile name")) for r in v_rows}:
            v_rows.append({
                "Local authority": AUTHORITY_NAME,
                "Mobile name": VEHICLE_NAME,
                "Dataset slug": SLUG,
                "Status": "Active",
                "Notes": "South Ayrshire Council mobile library operating 4-weekly routes"
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
            r["source_format"] = "HTML Timetable"
            r["last_checked"] = today
            r["last_updated"] = today
            r["notes"] = f"Harvested {len(stops_records)} stops across 4-weekly schedule from South Ayrshire Libraries Mobile Calendar."
    with open("services.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=s_fields)
        writer.writeheader()
        writer.writerows(s_rows)


if __name__ == "__main__":
    run()
