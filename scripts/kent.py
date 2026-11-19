"""
Kent County Council Mobile Library Ingestion Script
Harvests all mobile library stops from Kent County Council HTML Directory:
https://local.kent.gov.uk/kb5/kent/directory/results.page?communitychannel=8
Writes data/kent.csv, validates schema compliance, and updates services.csv, geocache, and historical vehicle registries.
"""

from _common import batch_lookup_postcodes, clean_time_24h
import os
import re
import ssl
import time
import json
import csv
import urllib.request
from datetime import datetime
from bs4 import BeautifulSoup
from frictionless import Resource, Schema

AUTHORITY_NAME = "Kent"
AUTHORITY_CODE = "E10000016"
SLUG = "kent"

BASE_URL = "https://local.kent.gov.uk/kb5/kent/directory"
LIST_URL = f"{BASE_URL}/results.page?communitychannel=8&nh=100&sr="
SERVICE_URL = f"{BASE_URL}/service.page?id="

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

# Disable SSL verification due to certificate chain issues on local.kent.gov.uk
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE






def fetch_url(url, retries=3, delay=0.5):
    """Fetch URL as UTF-8 HTML with linear backoff retries using the unverified SSL context.
    Returns decoded HTML or None if all retries fail."""
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=25) as resp:
                return resp.read().decode('utf-8', errors='ignore')
        except Exception as e:
            if attempt == retries - 1:
                print(f"Error fetching {url}: {e}")
                return None
            time.sleep(delay * (attempt + 1))
    return None


def run():
    """Discover Kent directory pages, extract stops, geocode postcodes, write data/kent.csv,
    validate against the schema, and update geocache, vehicle history, and services.csv."""
    print(f"[{SLUG}] Starting discovery and harvest for {AUTHORITY_NAME} ({AUTHORITY_CODE})...")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", SLUG, timestamp)
    os.makedirs(raw_dir, exist_ok=True)
    raw_services_dir = os.path.join(raw_dir, "services")
    os.makedirs(raw_services_dir, exist_ok=True)

    # Load persistent geocache
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    # Step 1: Discover all service IDs
    sr = 0
    service_ids = []
    while True:
        url = f"{LIST_URL}{sr}"
        print(f"[{SLUG}] Fetching directory results page sr={sr}...")
        raw_list_file = os.path.join(raw_dir, f"results_sr_{sr}.html")
        if os.path.exists(raw_list_file):
            with open(raw_list_file, "r", encoding="utf-8") as f:
                html = f.read()
        else:
            html = fetch_url(url)
            if not html:
                break
            with open(raw_list_file, "w", encoding="utf-8") as f:
                f.write(html)

        matches = re.findall(r'href=[\'"](?:/kb5/kent/directory/)?service\.page\?id=([^\'&"]+)', html)
        if not matches:
            break
        
        new_ids = [m for m in matches if m not in service_ids]
        if not new_ids:
            break
        
        service_ids.extend(new_ids)
        print(f"[{SLUG}] Found {len(new_ids)} new services (total collected: {len(service_ids)})")
        
        # LIST_URL requests nh=100 results per page; fewer indicates the final page
        if len(new_ids) < 100:
            break
        
        sr += 100
        time.sleep(0.3)

    print(f"[{SLUG}] Total Kent service pages to process: {len(service_ids)}")

    # Step 2: Fetch and parse each service page
    parsed_records = []
    postcodes_to_lookup = set()
    vehicles_seen = set()

    for idx, sid in enumerate(service_ids):
        raw_path = os.path.join(raw_services_dir, f"{sid}.html")
        if os.path.exists(raw_path):
            with open(raw_path, "r", encoding="utf-8") as f:
                html = f.read()
        else:
            time.sleep(0.12)
            surl = f"{SERVICE_URL}{sid}&communitychannel=8"
            html = fetch_url(surl)
            if not html:
                continue
            with open(raw_path, "w", encoding="utf-8") as f:
                f.write(html)
        
        soup = BeautifulSoup(html, "html.parser")
        
        h1 = soup.find("h1")
        h1_text = h1.get_text(strip=True) if h1 else ""
        
        community = ""
        stop_name = ""
        vehicle = ""
        
        # Expect "Community, Stop - mobile library stop (Vehicle)" or fallback without community
        m_h1 = re.match(r"^(.*?),\s*(.*?)\s*-\s*mobile library stop\s*\((.*?)\)", h1_text, re.IGNORECASE)
        if m_h1:
            community = m_h1.group(1).strip()
            stop_name = m_h1.group(2).strip()
            vehicle = m_h1.group(3).strip()
        else:
            m_h1_alt = re.match(r"^(.*?)\s*-\s*mobile library stop\s*\((.*?)\)", h1_text, re.IGNORECASE)
            if m_h1_alt:
                stop_name = m_h1_alt.group(1).strip()
                community = stop_name
                vehicle = m_h1_alt.group(2).strip()
            else:
                stop_name = h1_text
                community = h1_text
                vehicle = "Kent Mobile Library"

        if not vehicle:
            vehicle = "Kent Mobile Library"
        vehicles_seen.add(vehicle)

        main_elem = soup.find(id="page-content-main")
        main_text = main_elem.get_text("\n", strip=True) if main_elem else ""

        # Postcode extraction
        postcode = ""
        pc_match = re.search(r"Postcode\s+([A-Z]{1,2}[0-9][0-9A-Z]?\s*[0-9][A-Z]{2})", main_text, re.IGNORECASE)
        if pc_match:
            postcode = pc_match.group(1).strip().upper()
        
        # Address extraction
        # Positive lookahead stops at the next field label without consuming it
        addr_match = re.search(r"Address\s*\n(.*?)(?=\nPostcode|\nView|\nGet directions)", main_text, re.DOTALL)
        if addr_match:
            lines = [l.strip() for l in addr_match.group(1).strip().split("\n") if l.strip()]
            address = ", ".join(lines)
        else:
            address = f"{stop_name}, {community}" if community != stop_name else stop_name

        # Timing and Day extraction
        day = ""
        arr_24 = ""
        dep_24 = ""
        frequency = 2  # default fortnightly for Kent ("Every other ...")

        # Check for frequency mention
        if "every week" in main_text.lower() or "weekly" in main_text.lower():
            frequency = 1
        elif "every other" in main_text.lower() or "alternate" in main_text.lower() or "fortnightly" in main_text.lower():
            frequency = 2
        elif "monthly" in main_text.lower() or "every 4 weeks" in main_text.lower():
            frequency = 4

        # Search for Day & Times in text
        time_match = re.search(
            r"(?:every other|every|alternate)?\s*(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)[^\d\n]*[:\s]+(\d{1,2}:[0-5]\d\s*[ap]m|\d{1,2}\s*[ap]m)\s*(?:to|and|-)\s*(\d{1,2}:[0-5]\d\s*[ap]m|\d{1,2}\s*[ap]m)",
            main_text,
            re.IGNORECASE
        )
        if time_match:
            day = time_match.group(1).title()
            arr_24 = clean_time_24h(time_match.group(2))
            dep_24 = clean_time_24h(time_match.group(3))
        else:
            # Fallback
            day_match = re.search(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", main_text, re.IGNORECASE)
            if day_match:
                day = day_match.group(1).title()
            t_span = re.search(r"(\d{1,2}:[0-5]\d\s*[ap]m|\d{1,2}\s*[ap]m)\s*(?:to|and|-)\s*(\d{1,2}:[0-5]\d\s*[ap]m|\d{1,2}\s*[ap]m)", main_text, re.IGNORECASE)
            if t_span:
                arr_24 = clean_time_24h(t_span.group(1))
                dep_24 = clean_time_24h(t_span.group(2))

        # In case departure is empty or before arrival
        # Default to a 30-minute stop duration when no departure time is listed
        if arr_24 and not dep_24:
            try:
                ah, am = map(int, arr_24.split(":"))
                am += 30
                if am >= 60:
                    ah = (ah + 1) % 24
                    am -= 60
                dep_24 = f"{ah:02d}:{am:02d}"
            except Exception:
                dep_24 = ""

        # Route info
        route_name = ""
        route_match = re.search(r"This is a\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)*\s+route)", main_text, re.IGNORECASE)
        if route_match:
            route_name = f"{vehicle} {route_match.group(1).title()}"
        else:
            route_name = f"{vehicle} {day}" if day else vehicle

        # Stop Type
        stop_type = "Public"
        if "school" in stop_name.lower() or "nursery" in stop_name.lower():
            stop_type = "Private"

        parsed_records.append({
            "id": sid,
            "community": community,
            "stop": stop_name,
            "address": address,
            "postcode": postcode,
            "day": day,
            "start": arr_24,
            "end": dep_24,
            "frequency": frequency,
            "vehicle": vehicle,
            "route": route_name,
            "type": stop_type,
            "url": f"{SERVICE_URL}{sid}&communitychannel=8"
        })

        if postcode:
            postcodes_to_lookup.add(postcode)

        if (idx + 1) % 50 == 0:
            print(f"[{SLUG}] Processed {idx + 1}/{len(service_ids)} stops...")

    print(f"[{SLUG}] Parsed {len(parsed_records)} stops. Geocoding {len(postcodes_to_lookup)} unique postcodes...")

    # Step 3: Batch geocoding
    needed_pcs = [pc for pc in postcodes_to_lookup if pc not in geocache]
    print(f"[{SLUG}] {len(needed_pcs)} postcodes to resolve via api.postcodes.io...")

    if needed_pcs:
        resolved = batch_lookup_postcodes(needed_pcs)
        for pc, coords in resolved.items():
            geocache[pc] = coords
            norm_pc = pc.replace(" ", "").upper()
            geocache[norm_pc] = coords
        print(f"[{SLUG}] Successfully resolved {len(resolved)} postcodes.")

        # Persist geocache
        with open(geocache_path, "w", encoding="utf-8") as f:
            json.dump(geocache, f, indent=2)

    # Step 4: Assemble schema-compliant dataset
    stops_records = []
    fieldnames = [
        "Local authority", "Local authority code", "Mobile name", "Route", "Community",
        "Stop", "Address", "Postcode", "GeoX", "GeoY", "Day", "Type", "Arrival",
        "Departure", "Frequency", "Start", "End", "Exceptions", "Timetable"
    ]

    for rec in parsed_records:
        pc = rec["postcode"]
        norm_pc = pc.replace(" ", "").upper() if pc else ""
        coords = geocache.get(pc) or geocache.get(norm_pc)
        lat = round(coords[0], 6) if coords and coords[0] else ""
        lng = round(coords[1], 6) if coords and coords[1] else ""

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": AUTHORITY_CODE,
            "Mobile name": rec["vehicle"],
            "Route": rec["route"],
            "Community": rec["community"],
            "Stop": rec["stop"],
            "Address": rec["address"],
            "Postcode": pc,
            "GeoX": lng,
            "GeoY": lat,
            "Day": rec["day"],
            "Type": rec["type"],
            "Arrival": rec["start"],
            "Departure": rec["end"],
            "Frequency": (f"FREQ=WEEKLY;INTERVAL={rec["frequency"]}" if str(rec["frequency"]).isdigit() else rec["frequency"]),
            "Start": "2026-01-01",
            "End": "2026-12-31",
            "Exceptions": "Bank holidays",
            "Timetable": rec["url"]
        })

    # Sort stops deterministically: Mobile name, Route, Arrival
    stops_records.sort(key=lambda r: (r["Mobile name"], r["Route"], r["Arrival"], r["Community"], r["Stop"]))

    out_csv = os.path.join("data", f"{SLUG}.csv")
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stops_records)

    print(f"[{SLUG}] Successfully written {len(stops_records)} stops to {out_csv}")

    # Step 5: Frictionless schema validation
    print(f"[{SLUG}] Running Frictionless schema validation...")
    schema = Schema("schemas/mobile-library-stops.json")
    schema.foreign_keys = []
    resource = Resource(out_csv, schema=schema)
    report = resource.validate()
    print(f"[{SLUG}] Validation result: valid={report.valid}, errors={len(report.flatten(['rowNumber', 'fieldNumber', 'code', 'message']))}")
    if not report.valid:
        for err in report.flatten(['rowNumber', 'fieldNumber', 'code', 'message'])[:10]:
            print(f"  Row {err[0]}, Field {err[1]}: [{err[2]}] {err[3]}")
    else:
        print(f"[{SLUG}] 0 schema errors! Validation successful.")

    # Step 6: Update historical vehicle registry
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
                    "Notes": "Extracted from Kent County Council directory service pages"
                })
                added += 1

        if added > 0:
            with open(vehicles_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=v_fieldnames)
                writer.writeheader()
                writer.writerows(existing_rows)
            print(f"[{SLUG}] Added {added} vehicles to historical vehicle registry.")

    # Step 7: Update services.csv
    services_csv = "services.csv"
    if os.path.exists(services_csv):
        rows = []
        with open(services_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            s_fieldnames = reader.fieldnames
            rows = list(reader)

        updated = False
        for r in rows:
            if r.get("slug") == SLUG or r.get("gss_code") == AUTHORITY_CODE:
                r["status"] = "Active"
                r["dataset_status"] = "Ingested"
                r["stop_count"] = str(len(stops_records))
                r["format"] = "HTML Directory"
                r["source_url"] = "https://local.kent.gov.uk/kb5/kent/directory/results.page?communitychannel=8"
                r["notes"] = f"Harvested {len(stops_records)} stops across Ashford, Dover, Maidstone, Northfleet, Sturry mobile libraries."
                updated = True
                break

        if updated:
            with open(services_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=s_fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"[{SLUG}] Updated services.csv record for Kent.")


if __name__ == "__main__":
    run()
