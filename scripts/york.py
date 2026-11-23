"""
Ingestion script for Explore York Mobile Library Service (City of York Council).
Harvests routes, timetables, and stops from Explore York official portal
(exploreyork.org.uk/getting-involved/mobile-library/).
Geocodes via postcodes.io, validates schema compliance, and updates services.csv and geocache.
"""

from _common import bulk_lookup_postcodes, clean_time, create_mobile_library_file, parse_time_range
import os
import re
import csv
import json
from datetime import datetime
import urllib.request
from bs4 import BeautifulSoup
from frictionless import Resource, Schema

DATASET_SLUG = "york"
AUTHORITY_NAME = "York"
GSS_CODE = "E06000014"
BASE_URL = "https://exploreyork.org.uk/getting-involved/mobile-library/"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}

MAPSERVER_URL = (
    "https://maps.york.gov.uk/arcgis/rest/services/Public/LV_LeisureCulture/MapServer/8/query?"
    "where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=json"
)

# Curated postcodes for York stops
POSTCODE_MAP = {
    "skelton-brecksfield": "YO30 1YF",
    "osbaldwick-theleyes": "YO10 3PR",
    "deighton": "YO19 6HD",
    "heslington-mainstreet": "YO10 5EA",
    "naburn-school": "YO19 4PP",
    "hopgrovelanesouth": "YO32 9TG",
    "stocktonlane-beansway": "YO31 1HW",
    "stocktonontheforest-gaymeadow": "YO32 9UJ",
    "stocktonontheforest-villagehall": "YO32 9UP",
    "stocktonontheforest-westfieldhouse": "YO32 9UN",
    "holtby-churchrise": "YO19 5UQ",
    "murton-murtongarth": "YO19 5UL",
    "acastermalbis-mountpleasant": "YO23 2UQ",
    "askhambryan-thepub": "YO23 3QS",
    "askhamrichard-roseandcrown": "YO23 3PT",
    "hessay": "YO26 8JS",
    "rufforth-milestoneavenue": "YO23 3PX",
    "osbaldwickvillage(nearthepub)": "YO10 3NP",
    "badgerhill-yarburghway": "YO10 5HJ",
    "appletreevillage-meadlands": "YO31 0PA",
    "mistralcourt": "YO10 3RN",
    "stocktonlane-charlesmoor": "YO31 1JZ",
    "fieldcourt": "YO10 3RA",
    "elvington-greyhorse": "YO41 4AA",
    "elvington-surgery": "YO41 4AB",
    "heworthwithout-communitycentre": "YO31 0HG",
    "woodthorpe-acornway": "YO24 2TN",
    "woodthorpe-ryecroftavenue": "YO24 2SB",
    "wheldrake-courtneys": "YO19 6BA",
    "wheldrake-valleyview": "YO19 6AW",
    "wheldrake-southbacklane": "YO19 6AT",
    "wheldrake-whiterosehouse": "YO19 6EE"
}

# Official council MapServer coordinates (City of York Council Layer 8)
OFFICIAL_YORK_COORDS = {
    "skelton-brecksfield": (-1.13029, 53.99931),
    "osbaldwick-theleyes": (-1.03578, 53.95657),
    "deighton": (-1.04706, 53.88992),
    "heslington-mainstreet": (-1.04595, 53.94571),
    "naburn-school": (-1.08945, 53.90235),
    "hopgrovelanesouth": (-1.02694, 53.98748),
    "stocktonlane-beansway": (-1.04025, 53.97405),
    "stocktonontheforest-gaymeadow": (-1.00107, 53.99289),
    "stocktonontheforest-villagehall": (-0.99495, 53.99992),
    "stocktonontheforest-westfieldhouse": (-0.98982, 54.00311),
    "holtby-churchrise": (-1.01060, 53.96623),
    "murton-murtongarth": (-1.01459, 53.96612),
    "acastermalbis-mountpleasant": (-1.10356, 53.90340),
    "askhambryan-thepub": (-1.16384, 53.92827),
    "askhamrichard-roseandcrown": (-1.18334, 53.92412),
    "hessay": (-1.20474, 53.97346),
    "rufforth-milestoneavenue": (-1.19409, 53.95537),
    "osbaldwickvillage(nearthepub)": (-1.03346, 53.95937),
    "badgerhill-yarburghway": (-1.03233, 53.95246),
    "appletreevillage-meadlands": (-1.04269, 53.96450),
    "mistralcourt": (-1.07053, 53.97375),
    "stocktonlane-charlesmoor": (-1.05932, 53.97029),
    "fieldcourt": (-1.05410, 53.96804),
    "elvington-greyhorse": (-0.93532, 53.92052),
    "elvington-surgery": (-0.94026, 53.92352),
    "heworthwithout-communitycentre": (-1.04574, 53.96837),
    "woodthorpe-acornway": (-1.12279, 53.93839),
    "woodthorpe-ryecroftavenue": (-1.12922, 53.93753),
    "wheldrake-courtneys": (-0.96353, 53.89807),
    "wheldrake-valleyview": (-0.97429, 53.89473),
    "wheldrake-southbacklane": (-0.95763, 53.89789),
    "wheldrake-whiterosehouse": (-0.96296, 53.89643)
}








def main():
    """Fetch Explore York timetable HTML, geocode stops via POSTCODE_MAP and postcodes.io, write data/york.csv, and update metadata."""
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)
    raw_html_path = os.path.join(raw_dir, "explore_york_mobile_library.html")

    print(f"[{DATASET_SLUG}] Fetching timetable from {BASE_URL}")
    req = urllib.request.Request(BASE_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        html_content = resp.read().decode("utf-8")

    with open(raw_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[{DATASET_SLUG}] Saved raw HTML to {raw_html_path}")

    soup = BeautifulSoup(html_content, "html.parser")
    table = soup.find("table")
    if not table:
        raise ValueError("Could not find timetable table on Explore York page")

    raw_entries = []

    for tr in table.find_all("tr"):
        tds = tr.find_all(["td", "th"])
        if not tds or tds[0].name == "th":
            continue

        p_lists = [[p.get_text(strip=True) for p in td.find_all("p")] for td in tds]
        # Fallback if no <p> tags
        if not any(p_lists):
            p_lists = [[td.get_text(strip=True)] for td in tds]

        # Check if row has multiple distinct entries (like Row 23 with two <p> in each cell)
        max_p = max(len(p) for p in p_lists)
        if max_p > 1 and all(len(p) == max_p for p in p_lists):
            for idx in range(max_p):
                raw_entries.append({
                    "week": p_lists[0][idx],
                    "day": p_lists[1][idx],
                    "time_slot": p_lists[2][idx],
                    "location_raw": p_lists[3][idx]
                })
        else:
            # Join fragments in cells (e.g. 'Woodthorpe - Ryecroft' + 'Avenue')
            joined = [" ".join(p).strip() for p in p_lists]
            if len(joined) >= 4 and joined[0] in ["1", "2"]:
                raw_entries.append({
                    "week": joined[0],
                    "day": joined[1],
                    "time_slot": joined[2],
                    "location_raw": joined[3]
                })

    print(f"[{DATASET_SLUG}] Extracted {len(raw_entries)} raw stop rows from table.")

    # Determine postcodes to lookup
    lookup_pcs = []
    processed_stops = []

    CLEAN_MAP = {re.sub(r'[^a-z0-9]', '', k.lower()): v for k, v in POSTCODE_MAP.items()}

    for item in raw_entries:
        loc_raw = item["location_raw"].strip()
        arr, dep = parse_time_range(item["time_slot"])
        if not arr or not dep:
            continue

        # Split location into Community and Stop
        if "–" in loc_raw:
            parts = loc_raw.split("–", 1)
            comm = parts[0].strip()
            stop = parts[1].strip()
        elif "-" in loc_raw:
            parts = loc_raw.split("-", 1)
            comm = parts[0].strip()
            stop = parts[1].strip()
        else:
            comm = loc_raw
            stop = loc_raw

        k1 = re.sub(r"[^a-z0-9]", "", f"{comm}{stop}".lower())
        k2 = re.sub(r"[^a-z0-9]", "", comm.lower())
        k3 = re.sub(r"[^a-z0-9]", "", stop.lower())
        k4 = re.sub(r"[^a-z0-9]", "", loc_raw.lower())
        pc = CLEAN_MAP.get(k1) or CLEAN_MAP.get(k2) or CLEAN_MAP.get(k3) or CLEAN_MAP.get(k4) or ""
        if pc:
            lookup_pcs.append(pc)

        processed_stops.append({
            "week": item["week"],
            "day": item["day"],
            "time_slot": item["time_slot"],
            "arr": arr,
            "dep": dep,
            "community": comm,
            "stop": stop,
            "norm_key": k1,
            "postcode": pc
        })

    coords_cache = bulk_lookup_postcodes(lookup_pcs)

    # Load existing geocache
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    stops_records = []
    for item in processed_stops:
        comm = item["community"]
        stop = item["stop"]
        pc = item["postcode"]

        lat, lng = None, None
        k_short = re.sub(r'[^a-z0-9]', '', f"{comm}-{stop}".lower())
        k_full = item["norm_key"]
        k_comm = re.sub(r'[^a-z0-9]', '', comm.lower())
        k_stop = re.sub(r'[^a-z0-9]', '', stop.lower())

        if k_short in OFFICIAL_YORK_COORDS:
            lng, lat = OFFICIAL_YORK_COORDS[k_short]
        elif k_full in OFFICIAL_YORK_COORDS:
            lng, lat = OFFICIAL_YORK_COORDS[k_full]
        elif k_stop in OFFICIAL_YORK_COORDS:
            lng, lat = OFFICIAL_YORK_COORDS[k_stop]
        elif k_comm in OFFICIAL_YORK_COORDS:
            lng, lat = OFFICIAL_YORK_COORDS[k_comm]
        elif pc in coords_cache:
            lat, lng = coords_cache[pc]

        address = f"{stop}, {comm}" if stop != comm else comm

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": GSS_CODE,
            "Mobile name": "Explore York Mobile Library",
            "Route": f"Week {item['week']} {item['day']}",
            "Community": comm,
            "Stop": stop,
            "Address": address,
            "Postcode": pc,
            "GeoX": round(float(lng), 5) if lng else "",
            "GeoY": round(float(lat), 5) if lat else "",
            "Day": item["day"],
            "Type": "Public",
            "Arrival": item["arr"],
            "Departure": item["dep"],
            "Frequency": "FREQ=WEEKLY;INTERVAL=2",
            "Start": "2026-01-12",
            "End": "2026-12-31",
            "Exceptions": '',
            "Timetable": BASE_URL
        })

    print(f"[{DATASET_SLUG}] Prepared {len(stops_records)} validated stop records.")

    # Write output CSV using standard creator
    output_path = os.path.join("data", f"{DATASET_SLUG}.csv")
    create_mobile_library_file("york.csv", stops_records)
    print(f"[{DATASET_SLUG}] Saved dataset to data/york.csv")

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
                    row["source_url"] = BASE_URL
                    row["source_format"] = "HTML"
                    row["last_checked"] = date_stamp
                    row["last_updated"] = date_stamp
                    row["notes"] = f"Harvested {len(stops_records)} stops across Week 1 and Week 2 fortnightly schedule from Explore York."
                rows.append(row)
        with open(services_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fn)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[{DATASET_SLUG}] Updated {services_path}")

    # Update vehicle registry
    v_path = os.path.join("history", "historical_mobile_vehicles.csv")
    if os.path.exists(v_path):
        with open(v_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            v_fn = reader.fieldnames
            v_rows = list(reader)
        existing = {r["Mobile name"] for r in v_rows if r["Local authority"] == AUTHORITY_NAME}
        if "Explore York Mobile Library" not in existing:
            v_rows.append({
                "Local authority": AUTHORITY_NAME,
                "Mobile name": "Explore York Mobile Library",
                "Dataset slug": DATASET_SLUG,
                "Status": "Active",
                "Notes": "Operated by Explore York Libraries and Archives Mutual Ltd (Manager: Dean Audsley)."
            })
            with open(v_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=v_fn)
                writer.writeheader()
                writer.writerows(v_rows)
            print(f"[{DATASET_SLUG}] Updated {v_path}")


if __name__ == "__main__":
    main()
