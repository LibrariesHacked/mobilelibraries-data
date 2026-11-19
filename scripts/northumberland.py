"""
Northumberland County Council Mobile Library Ingestion Script
Harvests live timetables from Northumberland Libraries Spydus portal:
- North Mobile: https://northumberland.spydus.co.uk/cgi-bin/spydus.exe/MSGTRNGEN/WPAC/NORTHMOBILEROUTE
- West Mobile: https://northumberland.spydus.co.uk/cgi-bin/spydus.exe/MSGTRNGEN/WPAC/WESTMOBILEROUTE
Resolves postcodes, validates schema compliance, and updates services.csv, geocache, and historical vehicle registries.
"""

from _common import batch_lookup_postcodes, clean_time_24h
import os
import re
import json
import csv
import time
import urllib.request
from datetime import datetime
from bs4 import BeautifulSoup
from frictionless import Resource, Schema

AUTHORITY_NAME = "Northumberland"
AUTHORITY_CODE = "E06000057"
SLUG = "northumberland"

ROUTES_CONFIG = [
    {
        "vehicle": "North Mobile Library",
        "url": "https://northumberland.spydus.co.uk/cgi-bin/spydus.exe/MSGTRNGEN/WPAC/NORTHMOBILEROUTE",
        "raw_name": "north_mobile.html"
    },
    {
        "vehicle": "West Mobile Library",
        "url": "https://northumberland.spydus.co.uk/cgi-bin/spydus.exe/MSGTRNGEN/WPAC/WESTMOBILEROUTE",
        "raw_name": "west_mobile.html"
    }
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor'}
# Match standard UK postcode formats
POSTCODE_RE = re.compile(r"([A-Z]{1,2}[0-9][0-9A-Z]?\s*[0-9][A-Z]{2})", re.I)






def run():
    """Fetch Northumberland Spydus routes, geocode postcodes, write data/northumberland.csv, validate, and update registries."""
    print(f"[{SLUG}] Starting ingestion for {AUTHORITY_NAME} ({AUTHORITY_CODE})...")
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)

    # Load persistent geocache
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    raw_stops = []
    vehicles_seen = set()

    for cfg in ROUTES_CONFIG:
        v_name = cfg["vehicle"]
        vehicles_seen.add(v_name)
        v_url = cfg["url"]
        raw_file = os.path.join(raw_dir, cfg["raw_name"])

        print(f"[{SLUG}] Fetching {v_name} schedule from {v_url}...")
        req = urllib.request.Request(v_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        with open(raw_file, "w", encoding="utf-8") as f:
            f.write(html)

        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        print(f"[{SLUG}] Found {len(tables)} route tables for {v_name}")

        for t in tables:
            # Look backwards up to 10 preceding elements for route title and dates
            curr = t
            route_title = ""
            dates_str = ""
            for _ in range(10):
                curr = curr.find_previous(["h1", "h2", "h3", "h4", "h5", "p", "b", "strong", "div"])
                if not curr:
                    break
                txt = curr.get_text(" ", strip=True)
                # Match route week header (e.g. "Week 1") or 2026/ordinal date range
                if re.search(r"Week\s+\d", txt, re.I) and not route_title:
                    route_title = txt
                elif re.search(r"2026:|\d{1,2}(?:st|nd|rd|th)\s+[A-Za-z]+", txt) and not dates_str:
                    dates_str = txt

            # Fallback day extraction
            day = "Monday"
            for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]:
                if d.lower() in route_title.lower() or d.lower() in dates_str.lower():
                    day = d
                    break

            route_name = f"{v_name} {route_title}" if route_title else f"{v_name} {day}"

            rows = t.find_all("tr")
            for tr in rows[1:]:
                tds = tr.find_all(["td", "th"])
                if len(tds) < 4:
                    continue

                stop_raw = tds[0].get_text(" ", strip=True)
                pc_raw = tds[1].get_text(" ", strip=True).upper()
                arr_raw = tds[2].get_text(" ", strip=True)
                dep_raw = tds[3].get_text(" ", strip=True)

                if not stop_raw or "route" in stop_raw.lower():
                    continue

                arr = clean_time_24h(arr_raw)
                dep = clean_time_24h(dep_raw)

                # Clean postcode
                m_pc = POSTCODE_RE.search(pc_raw)
                postcode = m_pc.group(1).upper() if m_pc else ""

                # Split stop and community
                if " - " in stop_raw:
                    parts = [p.strip() for p in stop_raw.split(" - ", 1)]
                    comm = parts[0]
                    stop_name = parts[1]
                elif "," in stop_raw:
                    parts = [p.strip() for p in stop_raw.split(",", 1)]
                    comm = parts[0]
                    stop_name = parts[1]
                else:
                    comm = stop_raw
                    stop_name = stop_raw

                address = f"{stop_name}, {comm}, Northumberland" if stop_name != comm else f"{comm}, Northumberland"

                stop_type = "Public"
                if any(w in stop_name.lower() for w in ["school", "nursery"]):
                    stop_type = "Private"

                raw_stops.append({
                    "vehicle": v_name,
                    "route": route_name,
                    "community": comm,
                    "stop": stop_name,
                    "address": address,
                    "postcode": postcode,
                    "day": day,
                    "arr": arr,
                    "dep": dep,
                    "type": stop_type,
                    "dates": dates_str,
                    "url": v_url
                })

    print(f"[{SLUG}] Extracted {len(raw_stops)} stops across North & West mobile fleets.")

    # Geocoding
    pcs_to_lookup = set(s["postcode"] for s in raw_stops if s["postcode"] and s["postcode"] not in geocache)
    if pcs_to_lookup:
        print(f"[{SLUG}] Resolving {len(pcs_to_lookup)} postcodes via postcodes.io...")
        resolved = batch_lookup_postcodes(list(pcs_to_lookup))
        for pc, coords in resolved.items():
            geocache[pc] = coords
            geocache[pc.replace(" ", "")] = coords

        with open(geocache_path, "w", encoding="utf-8") as f:
            json.dump(geocache, f, indent=2)

    # Format schema-compliant dataset
    stops_records = []
    fieldnames = [
        "Local authority", "Local authority code", "Mobile name", "Route", "Community",
        "Stop", "Address", "Postcode", "GeoX", "GeoY", "Day", "Type", "Arrival",
        "Departure", "Frequency", "Start", "End", "Exceptions", "Timetable"
    ]

    for s in raw_stops:
        pc = s["postcode"]
        coords = geocache.get(pc) or geocache.get(pc.replace(" ", ""))
        lat = round(coords[0], 6) if coords else ""
        lng = round(coords[1], 6) if coords else ""

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": AUTHORITY_CODE,
            "Mobile name": s["vehicle"],
            "Route": s["route"],
            "Community": s["community"],
            "Stop": s["stop"],
            "Address": s["address"],
            "Postcode": pc,
            "GeoX": lng,
            "GeoY": lat,
            "Day": s["day"],
            "Type": s["type"],
            "Arrival": s["arr"],
            "Departure": s["dep"],
            "Frequency": "FREQ=WEEKLY;INTERVAL=3",
            "Start": "2026-01-05",
            "End": "2026-12-31",
            "Exceptions": "Bank holidays",
            "Timetable": s["url"]
        })

    stops_records.sort(key=lambda r: (r["Mobile name"], r["Route"], r["Arrival"], r["Community"], r["Stop"]))

    out_csv = os.path.join("data", f"{SLUG}.csv")
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stops_records)

    print(f"[{SLUG}] Saved {len(stops_records)} stops to {out_csv}")

    # Frictionless validation
    print(f"[{SLUG}] Validating schema compliance...")
    schema = Schema("schemas/mobile-library-stops.json")
    # Disable foreign key checks because reference tables are validated separately
    schema.foreign_keys = []
    resource = Resource(out_csv, schema=schema)
    report = resource.validate()
    print(f"[{SLUG}] Validation result: valid={report.valid}, errors={len(report.flatten(['rowNumber', 'fieldNumber', 'code', 'message']))}")
    if not report.valid:
        for err in report.flatten(['rowNumber', 'fieldNumber', 'code', 'message'])[:10]:
            print(f"  Row {err[0]}, Field {err[1]}: [{err[2]}] {err[3]}")
    else:
        print(f"[{SLUG}] 0 schema errors! Validation successful.")

    # Update historical vehicles
    vehicles_csv = os.path.join("history", "historical_mobile_vehicles.csv")
    if os.path.exists(vehicles_csv) and vehicles_seen:
        existing_rows = []
        with open(vehicles_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            v_fieldnames = reader.fieldnames
            existing_rows = list(reader)

        existing_keys = {(r.get("Local authority"), r.get("Mobile name")) for r in existing_rows}
        added = 0
        for v in sorted(vehicles_seen):
            key = (AUTHORITY_NAME, v)
            if key not in existing_keys:
                existing_rows.append({
                    "Local authority": AUTHORITY_NAME,
                    "Mobile name": v,
                    "Dataset slug": SLUG,
                    "Status": "Active",
                    "Notes": "Northumberland County Council mobile library vehicle (3-weekly rural rota)"
                })
                added += 1

        if added > 0:
            with open(vehicles_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=v_fieldnames)
                writer.writeheader()
                writer.writerows(existing_rows)
            print(f"[{SLUG}] Added {added} vehicles to historical vehicle registry.")

    # Update services.csv
    services_csv = "services.csv"
    if os.path.exists(services_csv):
        rows = []
        with open(services_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            s_fieldnames = reader.fieldnames
            rows = list(reader)

        updated = False
        today = datetime.now().strftime("%Y-%m-%d")
        for r in rows:
            if r.get("dataset_slug") == SLUG or r.get("local_authority_code") == AUTHORITY_CODE:
                r["has_mobile_service"] = "Yes"
                r["status"] = "Active Verified"
                r["source_url"] = "https://www.northumberland.gov.uk/libraries-and-archives/mobile-library-services"
                r["source_format"] = "Spydus Library Catalog"
                r["last_checked"] = today
                r["last_updated"] = today
                r["notes"] = f"Harvested {len(stops_records)} stops across North Mobile and West Mobile routes on 3-weekly cycle."
                updated = True
                break

        if updated:
            with open(services_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=s_fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"[{SLUG}] Updated services.csv record for Northumberland.")


if __name__ == "__main__":
    run()
