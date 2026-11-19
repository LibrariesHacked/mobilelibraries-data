"""
Ingestion script for East Riding of Yorkshire Mobile Library Service.
Harvests all 150 stops and live timetables directly from East Riding Libraries
DirectoryJS endpoints (directories 2 and 1), resolves postcodes and coordinates,
validates schema compliance, and updates services.csv and geocache.
"""

import os
import re
import csv
import json
import time
import html
from datetime import datetime
import urllib.request
from frictionless import Resource, Schema

DATASET_SLUG = "east_riding_of_yorkshire"
AUTHORITY_NAME = "East Riding of Yorkshire"
GSS_CODE = "E06000011"
BASE_URL = "https://www.eastridinglibraries.co.uk"
DIR2_URL = f"{BASE_URL}/index.php?option=com_erycdirectory&task=entrydata.fetchsearchentries&format=json&directory_id=2"
DIR1_URL = f"{BASE_URL}/index.php?option=com_erycdirectory&task=entrydata.fetchsearchentries&format=json&directory_id=1"
SOURCE_PAGE = f"{BASE_URL}/find-a-library/mobiles-and-at-home-service"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}


def get_json(url: str, retries: int = 3, delay: float = 1.0) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as e:
            if attempt == retries - 1:
                raise e
            time.sleep(delay)
    return {}


def clean_time(time_str: str) -> str:
    """Format time string into 24-hr HH:MM."""
    m = re.search(r"(\d{1,2})[:.;](\d{2})", time_str.strip())
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return ""


def batch_lookup_postcodes(postcodes_list: list) -> dict:
    """Lookup coordinates for up to 100 postcodes at a time via postcodes.io."""
    results = {}
    cleaned = list(set([pc.strip() for pc in postcodes_list if pc and pc.strip()]))
    for i in range(0, len(cleaned), 100):
        batch = cleaned[i:i+100]
        url = "https://api.postcodes.io/postcodes"
        req = urllib.request.Request(
            url,
            data=json.dumps({"postcodes": batch}).encode("utf-8"),
            headers={"User-Agent": "LibrariesHacked/1.0", "Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("result", []):
                    query_pc = item.get("query")
                    res = item.get("result")
                    if res:
                        results[query_pc] = {
                            "lat": res.get("latitude"),
                            "lng": res.get("longitude"),
                            "postcode": res.get("postcode")
                        }
        except Exception as e:
            print(f"Batch postcode error: {e}")
        time.sleep(0.3)
    return results


def main():
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)

    print(f"[{DATASET_SLUG}] Fetching Directory 2 (Venues)...")
    dir2_data = get_json(DIR2_URL)
    with open(os.path.join(raw_dir, "directory_2_venues.json"), "w", encoding="utf-8") as f:
        json.dump(dir2_data, f, indent=2)

    print(f"[{DATASET_SLUG}] Fetching Directory 1 (Schedules)...")
    dir1_data = get_json(DIR1_URL)
    with open(os.path.join(raw_dir, "directory_1_schedules.json"), "w", encoding="utf-8") as f:
        json.dump(dir1_data, f, indent=2)

    # Index schedules by normalized alias base
    # e.g. lib_aikemobilelibrary_default_normal -> aike
    schedules = {}
    for e in dir1_data.get("searchEntries", []):
        venue = e.get("search_data", {}).get("venue", "")
        if "mobile" in venue.lower():
            alias = e.get("alias", "")
            base = re.sub(r"[^a-z0-9]", "", alias.lower()).replace("lib", "").replace("mobilelibrarydefaultnormal", "")
            exceptions = e.get("search_data", {}).get("exceptions", [])
            valid_visits = [x for x in exceptions if x.get("Closed") == 0 and x.get("Times") and x["Times"][0].get("from")]
            schedules[base] = {
                "venue": venue,
                "visits": valid_visits
            }

    # Extract venues
    venues = []
    postcodes_to_lookup = []
    for e in dir2_data.get("searchEntries", []):
        alias = e.get("alias", "")
        if "mobile_library" in alias:
            base = re.sub(r"[^a-z0-9]", "", alias.lower()).replace("mobilelibrary", "")
            s_data = e.get("search_data", {})
            raw_name = s_data.get("name", [""])[0]
            name = html.unescape(raw_name).strip()
            contact = s_data.get("contact", [{}])[0] if isinstance(s_data.get("contact"), list) and s_data.get("contact") else {}
            pc = contact.get("postcode", "").strip()
            if pc:
                postcodes_to_lookup.append(pc)

            venues.append({
                "alias": alias,
                "base": base,
                "name": name,
                "building": contact.get("buildingName", "").strip(),
                "addr1": contact.get("addressLine1", "").strip(),
                "addr2": contact.get("addressLine2", "").strip(),
                "town": contact.get("townOrVillage", "").strip(),
                "postcode": pc
            })

    print(f"[{DATASET_SLUG}] Found {len(venues)} mobile library venues.")
    print(f"[{DATASET_SLUG}] Resolving {len(postcodes_to_lookup)} postcodes via postcodes.io batch...")
    geo_lookup = batch_lookup_postcodes(postcodes_to_lookup)

    stops_records = []

    for v in venues:
        base = v["base"]
        sched = schedules.get(base)
        if not sched:
            # try fuzzy match
            for sk, sv in schedules.items():
                if base in sk or sk in base:
                    sched = sv
                    break

        if not sched:
            print(f"Warning: No schedule found for {v['name']} ({v['alias']})")
            continue

        visits = sched["visits"]
        if not visits:
            continue

        # Extract dates and times
        visit_dates = []
        for vis in visits:
            d_str = vis.get("Date")
            if d_str:
                try:
                    visit_dates.append(datetime.strptime(d_str, "%Y-%m-%d"))
                except Exception:
                    pass

        sorted_dates = sorted(visit_dates)
        # Select current 2026/2027 window if available
        d_2026 = [d for d in sorted_dates if d.year >= 2026]
        target_dates = d_2026 if d_2026 else sorted_dates

        start_date = target_dates[0].strftime("%Y-%m-%d")
        end_date = target_dates[-1].strftime("%Y-%m-%d")
        day_name = target_dates[0].strftime("%A")

        # Arrival and Departure
        first_time = visits[0]["Times"][0]
        arrival = clean_time(first_time.get("from", ""))
        departure = clean_time(first_time.get("to", ""))

        # Frequency
        if len(target_dates) > 1:
            diffs = [(target_dates[i+1] - target_dates[i]).days for i in range(len(target_dates)-1)]
            avg_diff = sum(diffs) / len(diffs)
            if 24 <= avg_diff <= 32:
                freq = "FREQ=WEEKLY;INTERVAL=4"
            elif 12 <= avg_diff <= 16:
                freq = "FREQ=WEEKLY;INTERVAL=2"
            elif 6 <= avg_diff <= 8:
                freq = "FREQ=WEEKLY;INTERVAL=1"
            else:
                freq = f"FREQ=WEEKLY;INTERVAL={max(1, round(avg_diff / 7))}"
        else:
            freq = "FREQ=WEEKLY;INTERVAL=4"

        # Coordinates
        pc = v["postcode"]
        geo_info = geo_lookup.get(pc)
        if geo_info:
            geox = round(geo_info["lng"], 6)
            geoy = round(geo_info["lat"], 6)
            postcode = geo_info["postcode"]
        else:
            geox, geoy = "", ""
            postcode = pc

        # Community, Stop, Address
        community = v["town"] if v["town"] else v["name"].replace("Mobile Library", "").strip()
        stop_name = v["building"] or v["addr1"] or v["name"]
        if stop_name == v["name"] and "Mobile Library" in stop_name:
            stop_name = stop_name.replace("Mobile Library", "").strip()

        addr_parts = [p for p in [v["building"], v["addr1"], v["addr2"], v["town"]] if p]
        address = ", ".join(dict.fromkeys(addr_parts))

        route_name = f"{day_name} Route"
        timetable_url = f"{BASE_URL}/find-a-library/?entry={v['alias']}"

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": GSS_CODE,
            "Mobile name": "East Riding Mobile Library",
            "Route": route_name,
            "Community": community,
            "Stop": stop_name,
            "Address": address,
            "Postcode": postcode,
            "GeoX": geox,
            "GeoY": geoy,
            "Day": day_name,
            "Type": "Public",
            "Arrival": arrival,
            "Departure": departure,
            "Frequency": (f"FREQ=WEEKLY;INTERVAL={freq}" if str(freq).isdigit() else freq),
            "Start": start_date,
            "End": end_date,
            "Exceptions": "",
            "Timetable": timetable_url
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
                    row["source_url"] = SOURCE_PAGE
                    row["source_format"] = "JSON API / DirectoryJS"
                    row["last_checked"] = date_stamp
                    row["last_updated"] = date_stamp
                    row["notes"] = f"Harvested {len(stops_records)} stops from official DirectoryJS endpoints on {date_stamp}."
                rows.append(row)
        with open(services_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fn)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[{DATASET_SLUG}] Updated {services_path}")


if __name__ == "__main__":
    main()
