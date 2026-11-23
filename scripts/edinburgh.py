"""
City of Edinburgh Council Mobile Library Ingestion Script.
Harvests community mobile library routes and stops from:
1. City of Edinburgh Council Mobile Library Stops directory:
   https://www.edinburgh.gov.uk/directory/10194/mobile-library-stops
2. Official ArcGIS FeatureServer Layer (Mobile Library Community Route):
   https://services-eu1.arcgis.com/FgpikkYuSUOuITxp/arcgis/rest/services/Mobile_Library_Community_Route/FeatureServer/0

Extracts stop names, addresses, postcodes, times, fortnightly frequency, and exact coordinates.
Writes data/edinburgh.csv, validates against mobile-library-stops schema.
"""

import os
import re
import csv
import json
import time
import urllib.request
from datetime import datetime
from bs4 import BeautifulSoup
from frictionless import Resource

from _common import (
    create_mobile_library_file,
    batch_lookup_postcodes,
    clean_time,
    parse_time_range,
    sanitize_text,
    sanitize_row
)

AUTHORITY_NAME = "City of Edinburgh"
AUTHORITY_CODE = "S12000036"
DATASET_SLUG = "edinburgh"
SOURCE_URL = "https://www.edinburgh.gov.uk/directory/10194/mobile-library-stops"
ARCGIS_FS_URL = "https://services-eu1.arcgis.com/FgpikkYuSUOuITxp/arcgis/rest/services/Mobile_Library_Community_Route/FeatureServer/0/query?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=json"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}


def extract_community(stop_name: str, address: str) -> str:
    """Extract sensible community / neighborhood name from stop or address."""
    comm_map = [
        ("Alnwickhill", "Alnwickhill"),
        ("Barnton", "Barnton"),
        ("Barntongate", "Barnton"),
        ("Bonnington", "Bonnington"),
        ("Broomhouse", "Broomhouse"),
        ("Buckstone", "Buckstone"),
        ("Cammo", "Cammo"),
        ("Carrickvale", "Carrickvale"),
        ("Claremont", "Claremont"),
        ("Clark Road", "Trinity"),
        ("Craiglockhart", "Craiglockhart"),
        ("Craigmount", "Corstorphine"),
        ("Dalmeny", "Dalmeny"),
        ("Dumbiedykes", "Dumbiedykes"),
        ("Forrester Park", "Corstorphine"),
        ("Foulis", "Baberton"),
        ("Gillsland", "Merchiston"),
        ("Gilmerton", "Gilmerton"),
        ("Glenvarloch", "Liberton"),
        ("Gogarbank", "Gogarbank"),
        ("Hermiston", "Hermiston"),
        ("Howdenhall", "Howdenhall"),
        ("Liberton", "Liberton"),
        ("Magdalene", "Portobello"),
        ("Merrilees", "Baberton"),
        ("Mortonhall", "Mortonhall"),
        ("Newbridge", "Newbridge"),
        ("Newcraighall", "Newcraighall"),
        ("Pilrig", "Pilrig"),
        ("Prestonfield", "Prestonfield"),
        ("Ratho Station", "Ratho Station"),
        ("Redhall", "Redhall"),
        ("Ripple Project", "Restalrig"),
        ("Restalrig", "Restalrig"),
        ("Saughton", "Saughton"),
        ("South Queensferry", "South Queensferry"),
        ("Turnhouse", "Turnhouse"),
        ("Walter Scott", "Gilmerton"),
        ("Whitehouse", "Cramond"),
    ]
    combined = f"{stop_name} {address}"
    for k, v in comm_map:
        if k.lower() in combined.lower():
            return v
    return stop_name.split(",")[0].split("-")[0].strip()


def run():
    print(f"[{DATASET_SLUG}] Starting harvest for {AUTHORITY_NAME} ({AUTHORITY_CODE})...")
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)

    # 1. Fetch ArcGIS FeatureServer pins
    arcgis_file = os.path.join(raw_dir, "arcgis_features.json")
    if os.path.exists(arcgis_file):
        with open(arcgis_file, "r", encoding="utf-8") as f:
            arcgis_data = json.load(f)
    else:
        req = urllib.request.Request(ARCGIS_FS_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            arcgis_data = json.loads(resp.read().decode("utf-8"))
        with open(arcgis_file, "w", encoding="utf-8") as f:
            json.dump(arcgis_data, f, indent=2)

    fs_features = arcgis_data.get("features", [])
    print(f"[{DATASET_SLUG}] Loaded {len(fs_features)} official ArcGIS features")

    # Map ArcGIS features by title
    fs_lookup = {}
    for f in fs_features:
        attrs = f.get("attributes", {})
        title = attrs.get("Title", "")
        geom = f.get("geometry", {})
        if geom and "x" in geom and "y" in geom:
            fs_lookup[title] = (float(geom["y"]), float(geom["x"]))

    # 2. Scrape Directory records A-Z
    letters = ['A', 'B', 'C', 'D', 'F', 'G', 'H', 'L', 'M', 'N', 'P', 'R', 'S', 'T', 'W']
    scraped_stops_file = os.path.join(raw_dir, "scraped_directory_stops.json")
    
    if os.path.exists(scraped_stops_file):
        with open(scraped_stops_file, "r", encoding="utf-8") as f:
            scraped_records = json.load(f)
    else:
        directory_records = []
        base_url = "https://www.edinburgh.gov.uk"
        for letter in letters:
            url = f"{base_url}/directory/10194/a-to-z/{letter}"
            req = urllib.request.Request(url, headers=HEADERS)
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    soup = BeautifulSoup(r.read().decode("utf-8", errors="ignore"), "html.parser")
                    for a in soup.find_all("a", href=True):
                        if "/directory-record/" in a["href"]:
                            directory_records.append({
                                "title": a.get_text(strip=True),
                                "url": base_url + a["href"] if a["href"].startswith("/") else a["href"]
                            })
            except Exception as e:
                print(f"Error on letter {letter}: {e}")

        print(f"[{DATASET_SLUG}] Discovered {len(directory_records)} stop records in directory")

        scraped_records = []
        for rec in directory_records:
            req = urllib.request.Request(rec["url"], headers=HEADERS)
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    text = BeautifulSoup(r.read().decode("utf-8", errors="ignore"), "html.parser").get_text()
                    item = {"title": rec["title"], "url": rec["url"]}

                    pc_m = re.search(r'Postcode\s+([A-Z]{1,2}[0-9][0-9A-Z]?\s+[0-9][A-Z]{2})', text, re.I)
                    item["postcode"] = pc_m.group(1).upper() if pc_m else ""

                    addr_m = re.search(r'Address\s+(.*?)\s+Postcode', text, re.DOTALL)
                    item["address"] = sanitize_text(addr_m.group(1)) if addr_m else ""

                    dt_m = re.search(r'Day and time\s+(.*?)\s+Dates', text, re.DOTALL)
                    item["day_and_time"] = sanitize_text(dt_m.group(1)) if dt_m else ""

                    dates_m = re.search(r'Dates\s+(.*?)\s+Map', text, re.DOTALL)
                    item["dates"] = sanitize_text(dates_m.group(1)) if dates_m else ""

                    scraped_records.append(item)
            except Exception as e:
                print(f"Error fetching record {rec['url']}: {e}")
            time.sleep(0.05)

        with open(scraped_stops_file, "w", encoding="utf-8") as f:
            json.dump(scraped_records, f, indent=2)

    print(f"[{DATASET_SLUG}] Processing {len(scraped_records)} stop records...")

    # Batch lookup postcodes
    postcodes = [s["postcode"] for s in scraped_records if s.get("postcode")]
    pc_coords = batch_lookup_postcodes(postcodes)

    stops_data = []

    # Map stop titles to ArcGIS feature keys
    manual_arcgis_map = {
        "Alnwickhill Park": "Alnwickhill Park",
        "Barnton Whitehouse Road, opposite junction with Braehead Grove": "Barnton, Whitehouse Road",
        "Barntongate Avenue, near junction with Barntongate Drive": "Bartongate Avenue",
        "Bonnington Cottages (Bonnington Village)": "Bonnington Cottages (Bonnington Village)",
        "Broomhouse Crescent, Broomhouse Centre/St David's Broomhouse Church": "Broomhouse Crescent",
        "Buckstone Circle, near junction with Buckstone Shaw": "Buckstone Circle",
        "Cammo Grove, near junction with Cammo Hill": "Cammo Gardens",
        "Carrickvale Community Centre": "Carrickvale Community Centre",
        "Claremont Road, at Prospect Bank School": "Claremont Road",
        "Clark Road, adjacent to junction with Caithness Place": "Clark Road",
        "Craiglockhart Drive North, near junction with Craiglockhart Gardens": "Craiglockhart Drive North",
        "Craiglockhart Terrace Sheltered Housing": "Craiglockhart Terrace SH",
        "Craigmount View - corner with Stuart Square": "Stuart Square/Stuart Crescent (Red Stop)",
        "Dalmeny Square": "Dalmeny Village, Dalmeny Square.",
        "Dumbiedykes - Braidwood Centre": "Dumbiedykes, Braidwood Centre",
        "Forrester Park Avenue, at walkway between no. 16 & 18, where Mobile Polling Station is located": "Forrester Park Avenue",
        "Foulis Crescent, corner of Baberton Avenue": "Foulis Crescent, corner of Baberton Crescent",
        "Gillsland Grove Retirement Housing Scheme": "Gillsland Grove",
        "Gilmerton Rd, near junction with Walter Scott Avenue": "Gilmerton Road",
        "Glenvarloch Crescent, adjacent to playground/junction with Ringwood place": "Glenvarloch Crescent",
        "Gogarbank": "Gogar Bank",
        "Hermiston Village": "Hermiston Village",
        "Howdenhall Drive, adjacent to Howdenhall Court": "Howdenhall Drive",
        "Liberton Drive, between Liberton Brae and Alnwickhill Road": "Liberton Drive",
        "Magdalene Drive, layby at shops": "Magdalene Drive, layby at shops",
        "Merrilees Gate,  Baberton Avenue": "Merriliees Gate, Baberton Avenue",
        "Mortonhall Park Gardens, near junction with Mortonhall Park Avenue": "Mortonhall Park Gardens",
        "Newbridge, Parkside": "Newbridge, Parkside.",
        "Newcraighall Drive, between Newcraighall Road and Park View": "Newcraighall Drive",
        "Pilrig House Close": "Pilrig House Close",
        "Prestonfield Avenue, Prestonfield Neighbourhood Centre": "Prestonfield Avenue",
        "Ratho Station, Hillwood Rise, junction with Hillwood Terrace": "Ratho Station, Hillwood Rise",
        "Redhall Drive at junction with Redhall Gardens (triangle quadrant)": "Redhall Drive",
        "Ripple Project, Restalrig Road South": "Restalrig Road South (Ripple Project)",
        "Saughton Crescent, Bright Sparks Nursery/Murrayfield Nursery": "Saughton Cresent",
        "South Queensferry, Scotstoun, Queens Retreat": "Scotstoun, (Queen's Retreat), South Queensferry",
        "Turnhouse Road": "Turnhouse Road",
        "Turnhouse Road, Turnhouse Golf Club, Lennie Cottages": "Turnhouse Road - Turnhouse Golf Club/Lennie Cottages (Red Stop)",
        "Walter Scott Ave, adjacent to shops/Bellenden Gardens": "Walter Scott Avenue/Bellenden Gardens (Red Stop)",
        "Whitehouse Road - junction with Cramond Glebe Road": "Whitehouse Road, junction with Cramond Glebe Road",
    }

    for s in scraped_records:
        title = s["title"]
        addr = s.get("address", "") or title
        postcode = s.get("postcode", "")
        dt_raw = s.get("day_and_time", "")

        # Extract Day
        day = ""
        for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
            if d.lower() in dt_raw.lower():
                day = d
                break

        # Extract Times
        arrival = ""
        departure = ""
        time_part = re.sub(r'^.*?on\s+[A-Za-z]+,\s*', '', dt_raw)
        time_part = time_part.replace(' to ', ' - ')
        arr_dep = parse_time_range(time_part)
        if arr_dep:
            arrival, departure = arr_dep

        # Coordinates: prioritize official ArcGIS FeatureServer pins
        lat, lon = None, None
        arcgis_key = manual_arcgis_map.get(title)
        if arcgis_key and arcgis_key in fs_lookup:
            lat, lon = fs_lookup[arcgis_key]
        
        # Fallback to postcode lookup if needed or for Ratho Station
        if (lat is None or lon is None or title.startswith("Ratho Station")) and postcode in pc_coords:
            pc_pt = pc_coords[postcode]
            if pc_pt and pc_pt[0] is not None:
                lat, lon = pc_pt

        geox = f"{lon:.5f}" if lon is not None else ""
        geoy = f"{lat:.5f}" if lat is not None else ""

        community = extract_community(title, addr)
        route_name = f"{day} Route" if day else "Community Route"

        row = {
            "Local authority": AUTHORITY_NAME,
            "Local authority code": AUTHORITY_CODE,
            "Mobile name": "Edinburgh Mobile Library",
            "Route": route_name,
            "Community": community,
            "Stop": title,
            "Address": addr,
            "Postcode": postcode,
            "GeoX": geox,
            "GeoY": geoy,
            "Day": day,
            "Type": "Public",
            "Arrival": arrival,
            "Departure": departure,
            "Frequency": "FREQ=WEEKLY;INTERVAL=2",
            "Start": "2026-09-14",
            "End": "2026-12-31",
            "Exceptions": "",
            "Timetable": SOURCE_URL
        }
        stops_data.append(row)

    csv_filename = f"{DATASET_SLUG}.csv"
    create_mobile_library_file(csv_filename, stops_data)

    # Validate output
    output_path = os.path.join("data", csv_filename)
    res = Resource(output_path, schema="schemas/mobile-library-stops.json")
    report = res.validate()
    print(f"[{DATASET_SLUG}] Validation result: valid={report.valid}, errors={len(report.tasks[0].errors) if report.tasks else 0}")
    if not report.valid:
        for err in report.tasks[0].errors:
            print(f"  Validation error: {err.message}")


if __name__ == "__main__":
    run()
