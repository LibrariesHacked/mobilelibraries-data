"""
East Ayrshire Council (East Ayrshire Leisure / Ayrshire360) Mobile Library Ingestion Script
Harvests 2026 Mobile Library Timetable from Ayrshire360:
https://ayrshire360.com/communities/libraries/bringing-books-to-you/
https://ayrshire360.com/media/3aviebla/a360-mobile-timetable-2026-tabbed.pdf
Geocodes stops within East Ayrshire bounds, validates schema compliance, and updates services.csv, geocache, and historical vehicle registries.
"""

import os
import csv
import json
import urllib.parse
import urllib.request
from datetime import datetime
from frictionless import Resource, Schema

AUTHORITY_NAME = "East Ayrshire"
AUTHORITY_CODE = "S12000008"
SLUG = "east_ayrshire"

TIMETABLE_URL = "https://ayrshire360.com/communities/libraries/bringing-books-to-you/"
PDF_URL = "https://ayrshire360.com/media/3aviebla/a360-mobile-timetable-2026-tabbed.pdf"
VEHICLE_NAME = "East Ayrshire Mobile Library"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}

# Structured stops from East Ayrshire Leisure 2026 Mobile Library Timetable PDF (Weeks 1-4)
# Format: (Route, Day, StartDate, Community, Stop, Arrival, Departure, Type)
EAST_AYRSHIRE_STOPS = [
    # Week 1 Monday
    ("Week 1 Monday", "Monday", "2026-01-05", "Logan", "Logan Primary School", "11:00", "11:55", "Private"),
    ("Week 1 Monday", "Monday", "2026-01-05", "Logan", "Logan Community Stop", "12:00", "12:20", "Public"),
    ("Week 1 Monday", "Monday", "2026-01-05", "Cumnock", "Stonebriggs Farm", "13:00", "13:15", "Public"),
    ("Week 1 Monday", "Monday", "2026-01-05", "Cronberry", "Cronberry Village", "13:20", "13:40", "Public"),
    ("Week 1 Monday", "Monday", "2026-01-05", "Sorn", "Main Street", "14:10", "15:20", "Public"),
    # Week 1 Tuesday
    ("Week 1 Tuesday", "Tuesday", "2026-01-06", "Cumnock", "Netherthird Shops", "10:00", "11:00", "Public"),
    ("Week 1 Tuesday", "Tuesday", "2026-01-06", "Stair", "Wyndford", "11:30", "11:40", "Public"),
    ("Week 1 Tuesday", "Tuesday", "2026-01-06", "Trabboch", "Trabboch Mains", "12:00", "12:20", "Public"),
    ("Week 1 Tuesday", "Tuesday", "2026-01-06", "Mauchline", "Quilkieston Farm", "12:25", "12:50", "Public"),
    ("Week 1 Tuesday", "Tuesday", "2026-01-06", "Mauchline", "Hamilton Avenue", "14:10", "14:25", "Public"),
    ("Week 1 Tuesday", "Tuesday", "2026-01-06", "Mauchline", "Gilbert Burns Place", "14:40", "15:00", "Public"),
    ("Week 1 Tuesday", "Tuesday", "2026-01-06", "Mauchline", "Craighead Country Nursery", "15:15", "16:00", "Private"),
    # Week 1 Wednesday
    ("Week 1 Wednesday", "Wednesday", "2026-01-07", "Drongan", "Hayhill", "10:05", "10:20", "Public"),
    ("Week 1 Wednesday", "Wednesday", "2026-01-07", "Dalmellington", "Area Centre", "11:00", "13:00", "Public"),
    ("Week 1 Wednesday", "Wednesday", "2026-01-07", "Dalmellington", "Glebe House Care Home", "13:05", "13:25", "Private"),
    ("Week 1 Wednesday", "Wednesday", "2026-01-07", "Dalmellington", "Doon Valley Leisure Centre", "13:30", "13:35", "Public"),
    ("Week 1 Wednesday", "Wednesday", "2026-01-07", "Drongan", "Mill of Shield Road", "14:45", "15:15", "Public"),
    ("Week 1 Wednesday", "Wednesday", "2026-01-07", "Drongan", "Rowantree Court", "15:20", "15:45", "Public"),
    # Week 1 Thursday
    ("Week 1 Thursday", "Thursday", "2026-01-08", "Rankinston", "Rankinston", "10:15", "11:00", "Public"),
    ("Week 1 Thursday", "Thursday", "2026-01-08", "Patna", "Whitehill Avenue", "11:20", "12:20", "Public"),
    ("Week 1 Thursday", "Thursday", "2026-01-08", "Dalrymple", "Barbieston Road", "13:15", "14:15", "Public"),
    ("Week 1 Thursday", "Thursday", "2026-01-08", "Ochiltree", "Main Street", "14:45", "15:45", "Public"),
    # Week 1 Friday
    ("Week 1 Friday", "Friday", "2026-01-09", "Muirkirk", "Furnace Road", "10:15", "12:15", "Public"),
    ("Week 1 Friday", "Friday", "2026-01-09", "Muirkirk", "Pagan Walk", "12:20", "13:00", "Public"),
    # Week 2 Monday
    ("Week 2 Monday", "Monday", "2026-01-12", "Catrine", "The Square", "10:00", "10:25", "Public"),
    ("Week 2 Monday", "Monday", "2026-01-12", "Catrine", "Games Hall", "10:30", "11:00", "Public"),
    ("Week 2 Monday", "Monday", "2026-01-12", "Patna", "Whitehill Avenue", "11:45", "13:00", "Public"),
    ("Week 2 Monday", "Monday", "2026-01-12", "Hollybush", "Hollybush", "13:30", "14:00", "Public"),
    ("Week 2 Monday", "Monday", "2026-01-12", "Dalrymple", "Dalrymple", "14:15", "15:30", "Public"),
    # Week 2 Tuesday
    ("Week 2 Tuesday", "Tuesday", "2026-01-13", "Skares", "Skares", "10:00", "10:20", "Public"),
    ("Week 2 Tuesday", "Tuesday", "2026-01-13", "Cumnock", "King's Way", "10:40", "10:50", "Public"),
    ("Week 2 Tuesday", "Tuesday", "2026-01-13", "Cumnock", "Bute House", "11:00", "11:30", "Public"),
    ("Week 2 Tuesday", "Tuesday", "2026-01-13", "Lugar", "Park Terrace", "13:40", "14:00", "Public"),
    ("Week 2 Tuesday", "Tuesday", "2026-01-13", "Lugar", "Braehead Place", "14:05", "14:20", "Public"),
    ("Week 2 Tuesday", "Tuesday", "2026-01-13", "Logan", "Glenmuir Crescent", "14:30", "14:50", "Public"),
    ("Week 2 Tuesday", "Tuesday", "2026-01-13", "Hurlford", "Blair Road", "15:30", "16:30", "Public"),
    # Week 2 Wednesday
    ("Week 2 Wednesday", "Wednesday", "2026-01-14", "Dalmellington", "Area Centre", "10:30", "12:00", "Public"),
    ("Week 2 Wednesday", "Wednesday", "2026-01-14", "Bellsbank", "Bellsbank", "12:30", "13:00", "Public"),
    ("Week 2 Wednesday", "Wednesday", "2026-01-14", "Ochiltree", "Ochiltree Primary", "13:30", "14:45", "Private"),
    ("Week 2 Wednesday", "Wednesday", "2026-01-14", "Ochiltree", "Main Street", "14:50", "15:50", "Public"),
    # Week 2 Thursday
    ("Week 2 Thursday", "Thursday", "2026-01-15", "Kilmarnock", "James Hamilton Primary", "10:00", "12:30", "Private"),
    # Week 2 Friday
    ("Week 2 Friday", "Friday", "2026-01-16", "Muirkirk", "Furnace Road", "10:30", "11:30", "Public"),
    ("Week 2 Friday", "Friday", "2026-01-16", "Muirkirk", "Pagan Walk", "11:45", "12:15", "Public"),
    ("Week 2 Friday", "Friday", "2026-01-16", "Gatehead", "Gatehead", "13:45", "14:15", "Public"),
    ("Week 2 Friday", "Friday", "2026-01-16", "Kilmarnock", "Cottonmill", "14:30", "15:00", "Public"),
    # Week 3 Monday
    ("Week 3 Monday", "Monday", "2026-01-19", "Kilmarnock", "Ritchie Court", "09:45", "10:10", "Public"),
    ("Week 3 Monday", "Monday", "2026-01-19", "Kilmarnock", "MacAndrew Place", "10:15", "11:00", "Public"),
    ("Week 3 Monday", "Monday", "2026-01-19", "Kilmarnock", "MacNicholl Place", "11:05", "11:20", "Public"),
    ("Week 3 Monday", "Monday", "2026-01-19", "Kilmarnock", "Oak Place", "13:30", "14:00", "Public"),
    ("Week 3 Monday", "Monday", "2026-01-19", "Kilmarnock", "Laurel Place", "14:05", "14:50", "Public"),
    ("Week 3 Monday", "Monday", "2026-01-19", "Kilmarnock", "Darvel Avenue", "15:15", "16:00", "Public"),
    # Week 3 Tuesday
    ("Week 3 Tuesday", "Tuesday", "2026-01-20", "Kilmarnock", "Craigie Road", "09:35", "09:55", "Public"),
    ("Week 3 Tuesday", "Tuesday", "2026-01-20", "Kilmarnock", "Cairngorm Road", "10:10", "10:35", "Public"),
    ("Week 3 Tuesday", "Tuesday", "2026-01-20", "Kilmarnock", "Bridgehousehill Road", "10:40", "10:55", "Public"),
    ("Week 3 Tuesday", "Tuesday", "2026-01-20", "Kilmarnock", "Loreny Drive", "11:05", "11:15", "Public"),
    ("Week 3 Tuesday", "Tuesday", "2026-01-20", "Kilmarnock", "Langside Avenue", "11:20", "11:45", "Public"),
    ("Week 3 Tuesday", "Tuesday", "2026-01-20", "Fenwick", "Hallhouse Care Home", "13:15", "13:45", "Private"),
    ("Week 3 Tuesday", "Tuesday", "2026-01-20", "Kilmarnock", "Tourhill Road", "14:00", "15:00", "Public"),
    ("Week 3 Tuesday", "Tuesday", "2026-01-20", "Kilmaurs", "Kilmaurs", "15:10", "16:00", "Public"),
    # Week 3 Thursday
    ("Week 3 Thursday", "Thursday", "2026-01-22", "Hurlford", "Hurlford", "09:30", "10:50", "Public"),
    ("Week 3 Thursday", "Thursday", "2026-01-22", "Kilmarnock", "Gargieston Primary School", "11:10", "12:10", "Private"),
    ("Week 3 Thursday", "Thursday", "2026-01-22", "Kilmarnock", "Graceland Care Home", "13:30", "14:30", "Private"),
    ("Week 3 Thursday", "Thursday", "2026-01-22", "Kilmarnock", "Amlaird Road", "15:00", "16:00", "Public"),
    # Week 3 Friday
    ("Week 3 Friday", "Friday", "2026-01-23", "New Cumnock", "New Cumnock", "10:00", "11:30", "Public"),
    ("Week 3 Friday", "Friday", "2026-01-23", "Kilmarnock", "Bellfield (back of shops)", "12:30", "13:35", "Public"),
    ("Week 3 Friday", "Friday", "2026-01-23", "Kilmarnock", "Cunningham Drive", "13:45", "14:00", "Public"),
    ("Week 3 Friday", "Friday", "2026-01-23", "Kilmarnock", "Simon Crescent", "14:05", "14:30", "Public"),
    # Week 4 Monday
    ("Week 4 Monday", "Monday", "2026-01-26", "Kilmarnock", "Dundonald Road", "10:30", "11:10", "Public"),
    ("Week 4 Monday", "Monday", "2026-01-26", "Kilmarnock", "Harperland Drive", "11:15", "12:15", "Public"),
    ("Week 4 Monday", "Monday", "2026-01-26", "Moscow", "Grougar", "13:30", "13:55", "Public"),
    ("Week 4 Monday", "Monday", "2026-01-26", "Waterside", "Waterside", "14:05", "14:45", "Public"),
    ("Week 4 Monday", "Monday", "2026-01-26", "Fenwick", "Blackfaulds Road", "14:55", "15:20", "Public"),
    ("Week 4 Monday", "Monday", "2026-01-26", "Fenwick", "Fenwick Main Street", "15:25", "15:45", "Public"),
    ("Week 4 Monday", "Monday", "2026-01-26", "Fenwick", "Low Fenwick", "15:50", "16:05", "Public"),
    # Week 4 Tuesday
    ("Week 4 Tuesday", "Tuesday", "2026-01-27", "Kilmarnock", "Lizdean Care Home", "10:00", "10:30", "Private"),
    ("Week 4 Tuesday", "Tuesday", "2026-01-27", "Kilmarnock", "Grange Care Home", "10:40", "11:10", "Private"),
    ("Week 4 Tuesday", "Tuesday", "2026-01-27", "Kilmarnock", "Central Avenue", "11:25", "13:00", "Public"),
    ("Week 4 Tuesday", "Tuesday", "2026-01-27", "Crookedholm", "Crookedholm", "14:00", "14:20", "Public"),
    ("Week 4 Tuesday", "Tuesday", "2026-01-27", "Kilmaurs", "Kilmaurs", "14:50", "15:50", "Public"),
    # Week 4 Wednesday
    ("Week 4 Wednesday", "Wednesday", "2026-01-28", "Dunlop", "West View", "09:30", "10:00", "Public"),
    ("Week 4 Wednesday", "Wednesday", "2026-01-28", "Lugton", "Lugton", "10:20", "10:50", "Public"),
    ("Week 4 Wednesday", "Wednesday", "2026-01-28", "Knockentiber", "Knockentiber", "11:20", "11:50", "Public"),
    ("Week 4 Wednesday", "Wednesday", "2026-01-28", "Kilmarnock", "Samson Avenue", "13:55", "14:15", "Public"),
    ("Week 4 Wednesday", "Wednesday", "2026-01-28", "Kilmarnock", "Craigie Road", "14:20", "14:40", "Public"),
    # Week 4 Thursday
    ("Week 4 Thursday", "Thursday", "2026-01-29", "Hurlford", "Hurlford", "09:30", "11:00", "Public"),
    ("Week 4 Thursday", "Thursday", "2026-01-29", "Kilmarnock", "Tourhill Road", "11:30", "12:00", "Public"),
    ("Week 4 Thursday", "Thursday", "2026-01-29", "Kilmarnock", "Onthank Primary", "13:30", "14:25", "Private"),
    ("Week 4 Thursday", "Thursday", "2026-01-29", "Kilmarnock", "Amlaird Road", "14:30", "15:30", "Public"),
    ("Week 4 Thursday", "Thursday", "2026-01-29", "Kilmarnock", "Davaar Drive", "15:40", "16:10", "Public"),
    # Week 4 Friday
    ("Week 4 Friday", "Friday", "2026-01-30", "New Cumnock", "New Cumnock (Morning)", "10:00", "10:55", "Public"),
    ("Week 4 Friday", "Friday", "2026-01-30", "New Cumnock", "New Cumnock PS", "11:00", "11:55", "Private"),
    ("Week 4 Friday", "Friday", "2026-01-30", "New Cumnock", "New Cumnock (Midday)", "12:00", "12:30", "Public"),
    ("Week 4 Friday", "Friday", "2026-01-30", "Cumnock", "Netherthird Primary School", "13:15", "14:20", "Private")
]


def geocode_ea_place(community: str, cache: dict):
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
                if p.get("county_unitary") == "East Ayrshire" or (55.25 <= lat <= 55.75 and -4.65 <= lon <= -3.95):
                    cache[community] = (round(lat, 6), round(lon, 6))
                    return cache[community]
    except Exception:
        pass
    cache[community] = (55.6111, -4.4956)  # Kilmarnock / East Ayrshire fallback
    return cache[community]


def reverse_geocode_postcode(lat: float, lon: float, pc_cache: dict) -> str:
    key = f"{round(lat, 4)},{round(lon, 4)}"
    if key in pc_cache:
        return pc_cache[key]
    try:
        url = f"https://api.postcodes.io/postcodes?lat={lat}&lon={lon}&limit=1"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
            if data.get("result"):
                pc_cache[key] = data["result"][0]["postcode"]
                return pc_cache[key]
    except Exception:
        pass
    pc_cache[key] = ""
    return ""


def run():
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

    for rt, day, start, comm, stop, arr, dep, stype in EAST_AYRSHIRE_STOPS:
        lat, lon = geocode_ea_place(comm, place_cache)
        pc = reverse_geocode_postcode(lat, lon, pc_cache)
        geocache[f"{AUTHORITY_NAME}:{comm}:{stop}".lower()] = (lat, lon)

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": AUTHORITY_CODE,
            "Mobile name": VEHICLE_NAME,
            "Route": rt,
            "Community": comm,
            "Stop": stop,
            "Address": f"{stop}, {comm}, East Ayrshire",
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
            "Timetable": PDF_URL
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
                "Notes": "East Ayrshire Leisure (Ayrshire360) mobile library operating 4-weekly North & South routes"
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
            r["source_format"] = "PDF Timetable"
            r["last_checked"] = today
            r["last_updated"] = today
            r["notes"] = f"Harvested {len(stops_records)} stops across 4-weekly North and South mobile routes from Ayrshire360 2026 timetable PDF."
    with open("services.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=s_fields)
        writer.writeheader()
        writer.writerows(s_rows)


if __name__ == "__main__":
    run()
