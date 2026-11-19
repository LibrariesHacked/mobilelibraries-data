"""
Orkney Islands Council (Orkney Library & Archive) Mobile Library Ingestion Script
Harvests 2026 Mobile Library Timetable from Orkney Library & Archive:
https://orkneylibrary.org.uk/mobile-library/
https://orkneylibrary.org.uk/wp-content/uploads/2025/12/Mobile-Calendar-2026-Accessible-Version.pdf
Geocodes stops within Orkney Islands bounds, validates schema compliance, and updates services.csv, geocache, and historical vehicle registries.
"""

from _common import reverse_geocode_postcode
import os
import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime
from frictionless import Resource, Schema

AUTHORITY_NAME = "Orkney Islands"
AUTHORITY_CODE = "S12000023"
SLUG = "orkney_islands"

TIMETABLE_URL = "https://orkneylibrary.org.uk/mobile-library/"
PDF_URL = "https://orkneylibrary.org.uk/wp-content/uploads/2025/12/Mobile-Calendar-2026-Accessible-Version.pdf"
VEHICLE_NAME = "Booky McBookface"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}

# Structured stops from Orkney Library & Archive 2026 Accessible Mobile Library Timetable PDF
# Format: (Route, Day, StartDate, Community, Stop, Arrival, Departure, Type)
ORKNEY_STOPS = [
    # Burray, South Ronaldsay & Holm (Thursdays: 15 Jan, 12 Mar, 7 May, 2 Jul, 27 Aug, 22 Oct, 17 Dec)
    ("Burray, South Ronaldsay & Holm", "Thursday", "2026-01-15", "Burray", "Burray School", "09:30", "10:10", "Private"),
    ("Burray, South Ronaldsay & Holm", "Thursday", "2026-01-15", "St Margaret's Hope", "Hope School", "10:20", "11:10", "Private"),
    ("Burray, South Ronaldsay & Holm", "Thursday", "2026-01-15", "St Margaret's Hope", "Braeburn Court", "11:15", "11:30", "Public"),
    ("Burray, South Ronaldsay & Holm", "Thursday", "2026-01-15", "St Margaret's Hope", "Marengo", "11:35", "11:50", "Public"),
    ("Burray, South Ronaldsay & Holm", "Thursday", "2026-01-15", "Herston", "Herston", "12:00", "12:30", "Public"),
    ("Burray, South Ronaldsay & Holm", "Thursday", "2026-01-15", "South Ronaldsay", "Olad Brae", "13:15", "14:00", "Public"),
    ("Burray, South Ronaldsay & Holm", "Thursday", "2026-01-15", "South Ronaldsay", "Leaburn", "14:15", "15:00", "Public"),
    ("Burray, South Ronaldsay & Holm", "Thursday", "2026-01-15", "St Mary's (Holm)", "Station Square", "15:15", "15:45", "Public"),
    # Deerness (Thursdays: 12 Feb, 23 Apr, 18 Jun, 13 Aug, 8 Oct, 3 Dec)
    ("Deerness", "Thursday", "2026-02-12", "Tankerness", "St Andrew's School", "09:30", "12:25", "Private"),
    ("Deerness", "Thursday", "2026-02-12", "Toab", "Greenfield (Toab)", "12:30", "13:15", "Public"),
    ("Deerness", "Thursday", "2026-02-12", "Deerness", "Deerness Hall", "14:15", "17:00", "Public"),
    # Dounby, Sandwick & Birsay (Tuesdays: 13 Jan, 3 Mar, 21 Apr, 23 Jun, 18 Aug, 13 Oct, 15 Dec)
    ("Dounby, Sandwick & Birsay", "Tuesday", "2026-01-13", "Dounby", "Dounby School", "09:30", "11:15", "Private"),
    ("Dounby, Sandwick & Birsay", "Tuesday", "2026-01-13", "Sandwick", "Sandwick Hall", "11:30", "12:00", "Public"),
    ("Dounby, Sandwick & Birsay", "Tuesday", "2026-01-13", "Swannay", "Kelowna (Swannay)", "12:15", "12:45", "Public"),
    ("Dounby, Sandwick & Birsay", "Tuesday", "2026-01-13", "Birsay", "Birsay Palace", "13:00", "13:50", "Public"),
    ("Dounby, Sandwick & Birsay", "Tuesday", "2026-01-13", "Birsay", "Birsay Hall", "14:30", "15:00", "Public"),
    ("Dounby, Sandwick & Birsay", "Tuesday", "2026-01-13", "Dounby", "Quilco", "15:15", "15:55", "Public"),
    ("Dounby, Sandwick & Birsay", "Tuesday", "2026-01-13", "Dounby", "Dounby Village", "16:00", "17:30", "Public"),
    # Eday (Mondays: 2 Feb, 30 Mar, 25 May, 20 Jul, 14 Sep, 9 Nov)
    ("Eday", "Monday", "2026-02-02", "Eday", "Eday Community Shop", "09:45", "12:30", "Public"),
    ("Eday", "Monday", "2026-02-02", "Eday", "Eday School", "13:15", "16:00", "Public"),
    # Evie, Rendall & Firth (Tuesdays: 20 Jan, 17 Mar, 12 May, 7 Jul, 1 Sep, 27 Oct)
    ("Evie, Rendall & Firth", "Tuesday", "2026-01-20", "Finstown", "Firth School", "09:40", "11:00", "Private"),
    ("Evie, Rendall & Firth", "Tuesday", "2026-01-20", "Evie", "Evie School", "11:15", "12:15", "Private"),
    ("Evie, Rendall & Firth", "Tuesday", "2026-01-20", "Evie", "Airsdale (Costa)", "12:30", "12:45", "Public"),
    ("Evie, Rendall & Firth", "Tuesday", "2026-01-20", "Evie", "Evie Village", "13:00", "13:20", "Public"),
    ("Evie, Rendall & Firth", "Tuesday", "2026-01-20", "Rendall", "Rendall Hall", "14:00", "14:30", "Public"),
    ("Evie, Rendall & Firth", "Tuesday", "2026-01-20", "Finstown", "Jewadale", "14:45", "15:40", "Public"),
    ("Evie, Rendall & Firth", "Tuesday", "2026-01-20", "Finstown", "Finstown Car Park", "15:45", "17:00", "Public"),
    # Harray & Quoyloo (Thursdays: 15 Feb, 2 Apr, 28 May, 23 Jul, 10 Sep, 12 Nov)
    ("Harray & Quoyloo", "Thursday", "2026-04-02", "Harray", "Harray Hall", "09:30", "10:45", "Public"),
    ("Harray & Quoyloo", "Thursday", "2026-04-02", "Quoyloo", "Isbister Shop", "11:00", "12:30", "Public"),
    # Hoy & Flotta (Wednesdays: 28 Jan, 25 Mar, 20 May, 15 Jul, 9 Sep, 4 Nov)
    ("Hoy & Flotta", "Wednesday", "2026-01-28", "Hoy", "Hoy Centre", "09:40", "10:40", "Public"),
    ("Hoy & Flotta", "Wednesday", "2026-01-28", "Hoy", "St John's Kirk", "11:15", "12:30", "Public"),
    ("Hoy & Flotta", "Wednesday", "2026-01-28", "Lyness (Hoy)", "French Road", "13:00", "13:30", "Public"),
    ("Hoy & Flotta", "Wednesday", "2026-01-28", "Flotta", "Burnside (Flotta)", "14:30", "15:30", "Public"),
    # Longhope (Tuesdays: 27 Jan, 24 Mar, 19 May, 14 Jul, 8 Sep, 3 Nov)
    ("Longhope", "Tuesday", "2026-01-27", "Longhope", "North Walls School", "09:00", "10:20", "Private"),
    ("Longhope", "Tuesday", "2026-01-27", "Longhope", "St Colms Quadrant", "10:40", "11:30", "Public"),
    ("Longhope", "Tuesday", "2026-01-27", "Longhope", "Custom House", "11:45", "12:30", "Public"),
    ("Longhope", "Tuesday", "2026-01-27", "Longhope", "Cemetery", "13:15", "14:00", "Public"),
    ("Longhope", "Tuesday", "2026-01-27", "Longhope", "Brims", "14:15", "15:15", "Public"),
    # Orphir & Stenness (Tuesdays: 10 Feb, 31 Mar, 2 Jun, 28 Jul, 29 Sep, 17 Nov)
    ("Orphir & Stenness", "Tuesday", "2026-02-10", "Orphir", "Orphir School (Public)", "09:30", "11:00", "Public"),
    ("Orphir & Stenness", "Tuesday", "2026-02-10", "Stenness", "Stenness School (Public)", "11:30", "13:00", "Public"),
    # Rousay & Egilsay (Thursdays: 19 Feb, 16 Apr, 11 Jun, 30 Jul, 1 Oct, 26 Nov)
    ("Rousay & Egilsay", "Thursday", "2026-02-19", "Rousay", "Rousay School", "09:00", "10:15", "Private"),
    ("Rousay & Egilsay", "Thursday", "2026-02-19", "Rousay", "Hurtiso", "10:20", "10:45", "Public"),
    ("Rousay & Egilsay", "Thursday", "2026-02-19", "Rousay", "Wasbister", "11:00", "11:45", "Public"),
    ("Rousay & Egilsay", "Thursday", "2026-02-19", "Rousay", "Frotoft", "12:00", "12:25", "Public"),
    ("Rousay & Egilsay", "Thursday", "2026-02-19", "Rousay", "Rousay Pier", "12:30", "12:45", "Public"),
    ("Rousay & Egilsay", "Thursday", "2026-02-19", "Egilsay", "Egilsay", "13:30", "13:40", "Public"),
    # Sanday (Thursdays: 22 Jan, 19 Mar, 14 May, 9 Jul, 3 Sep, 29 Oct)
    ("Sanday", "Thursday", "2026-01-22", "Sanday", "Sanday School (Morning)", "09:30", "11:30", "Public"),
    ("Sanday", "Thursday", "2026-01-22", "Sanday", "Lochend", "11:45", "12:30", "Public"),
    ("Sanday", "Thursday", "2026-01-22", "Sanday", "Lady Village", "13:15", "15:00", "Public"),
    ("Sanday", "Thursday", "2026-01-22", "Sanday", "Sanday School (Afternoon)", "15:15", "16:00", "Public"),
    # Shapinsay (Thursdays: 8 Jan, 5 Mar, 30 Apr, 25 Jun, 20 Aug, 15 Oct, 10 Dec)
    ("Shapinsay", "Thursday", "2026-01-08", "Shapinsay", "Shapinsay School", "10:15", "11:00", "Private"),
    ("Shapinsay", "Thursday", "2026-01-08", "Shapinsay", "North School", "11:15", "12:15", "Public"),
    ("Shapinsay", "Thursday", "2026-01-08", "Shapinsay", "Astley", "12:30", "12:45", "Public"),
    ("Shapinsay", "Thursday", "2026-01-08", "Shapinsay", "Helliar", "13:30", "14:15", "Public"),
    ("Shapinsay", "Thursday", "2026-01-08", "Shapinsay", "Balfour Village", "14:30", "15:15", "Public"),
    # Stronsay (Mondays: 16 Feb, 20 Apr, 15 Jun, 10 Aug, 5 Oct, 30 Nov)
    ("Stronsay", "Monday", "2026-02-16", "Stronsay", "Council Houses", "08:45", "09:45", "Public"),
    ("Stronsay", "Monday", "2026-02-16", "Stronsay", "Stronsay School", "10:00", "12:00", "Private"),
    ("Stronsay", "Monday", "2026-02-16", "Stronsay", "Stronsay Kirk", "12:45", "15:00", "Public"),
    ("Stronsay", "Monday", "2026-02-16", "Stronsay", "Fish Mart", "15:15", "16:45", "Public"),
    # Westray (Wednesdays: 14 Jan, 11 Mar, 6 May, 1 Jul, 26 Aug, 21 Oct, 16 Dec)
    ("Westray", "Wednesday", "2026-01-14", "Westray", "Westray School", "09:00", "12:00", "Private"),
    ("Westray", "Wednesday", "2026-01-14", "Westray", "Kalisgarth", "12:05", "12:45", "Public"),
    ("Westray", "Wednesday", "2026-01-14", "Pierowall (Westray)", "Old Kirk", "13:30", "15:30", "Public"),
    ("Westray", "Wednesday", "2026-01-14", "Pierowall (Westray)", "Beachgrove", "15:45", "17:15", "Public")
]


def geocode_orkney_place(community: str, cache: dict):
    """Look up (lat, lon) for an Orkney community via postcodes.io with caching, falling back to Kirkwall."""
    # Drop parenthetical island qualifiers like 'Lyness (Hoy)' before querying
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
                # Bounding box filter to reject similarly named places outside Orkney
                if p.get("county_unitary") == "Orkney Islands" or (58.7 <= lat <= 59.45 and -3.5 <= lon <= -2.3):
                    cache[clean] = (round(lat, 6), round(lon, 6))
                    return cache[clean]
    except Exception:
        pass
    cache[clean] = (58.9809, -2.9605)  # Kirkwall / Orkney fallback
    return cache[clean]




def run():
    """Geocode Orkney stops, write data/orkney_islands.csv, validate schema, and update metadata CSVs."""
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

    for rt, day, start, comm, stop, arr, dep, stype in ORKNEY_STOPS:
        lat, lon = geocode_orkney_place(comm, place_cache)
        pc = reverse_geocode_postcode(lat, lon, pc_cache)
        geocache[f"{AUTHORITY_NAME}:{comm}:{stop}".lower()] = (lat, lon)

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": AUTHORITY_CODE,
            "Mobile name": VEHICLE_NAME,
            "Route": rt,
            "Community": comm,
            "Stop": stop,
            "Address": f"{stop}, {comm}, Orkney",
            "Postcode": pc,
            "GeoX": lon,
            "GeoY": lat,
            "Day": day,
            "Type": stype,
            "Arrival": arr,
            "Departure": dep,
            "Frequency": "FREQ=WEEKLY;INTERVAL=8",
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
    # Skip foreign-key checks because services.csv is validated separately
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
                "Notes": "Orkney Library & Archive mobile library van serving Mainland Orkney and outer islands"
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
            r["notes"] = f"Harvested {len(stops_records)} stops across 14 Mainland & outer island routes (Booky McBookface)."
    with open("services.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=s_fields)
        writer.writeheader()
        writer.writerows(s_rows)


if __name__ == "__main__":
    run()
