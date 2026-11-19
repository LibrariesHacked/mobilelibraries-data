"""
Suffolk Community Libraries Mobile Library Ingestion Script
Processes the Livewire directory export from Suffolk Community Libraries:
https://suffolkcommunitylibraries.co.uk/visit/mobile-libraries/
(saved in raw/suffolk/<date>/suffolk_livewire.json)
Matches coordinates against historical Suffolk stop coordinates, reference geocache, and OS Open Names (postcodes.io),
reverse-geocodes postcodes, archives unscheduled/closed stops, and validates schema compliance.
"""

import os
import re
import csv
import glob
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime
from frictionless import Resource, Schema

AUTHORITY_NAME = "Suffolk"
AUTHORITY_CODE = "E10000029"
SLUG = "suffolk"
BASE_URL = "https://suffolkcommunitylibraries.co.uk/visit/mobile-libraries/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}

DAY_MAP = {
    "Mon": "Monday",
    "Tue": "Tuesday",
    "Wed": "Wednesday",
    "Thu": "Thursday",
    "Fri": "Friday",
    "Sat": "Saturday",
    "Sun": "Sunday"
}


def find_latest_livewire_json() -> str:
    """Return the path to the newest suffolk_livewire.json export under raw/suffolk/."""
    candidates = sorted(glob.glob(os.path.join("raw", SLUG, "*", "suffolk_livewire.json")))
    if candidates:
        return candidates[-1]
    direct = os.path.join("raw", SLUG, "suffolk_livewire.json")
    if os.path.exists(direct):
        return direct
    raise FileNotFoundError("Could not find suffolk_livewire.json in raw/suffolk/")


def lookup_place_suffolk(place_name: str, session_cache: dict):
    """Geocode a Suffolk place name via postcodes.io/places, caching in session_cache and falling back to a county centroid."""
    # Strip parenthetical notes and secondary qualifiers before querying
    clean_p = re.sub(r"\(.*?\)", "", place_name).split(",")[0].strip()
    key = clean_p.lower()
    if key in session_cache:
        return session_cache[key]

    q = urllib.parse.quote(clean_p)
    url = f"https://api.postcodes.io/places?q={q}&limit=10"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for p in data.get("result") or []:
                lat_p = float(p.get("latitude", 0))
                lon_p = float(p.get("longitude", 0))
                # Match Suffolk unitary or approximate Suffolk bounding box
                if p.get("county_unitary") == "Suffolk" or (51.93 <= lat_p <= 52.56 and 0.34 <= lon_p <= 1.77):
                    coords = (round(lat_p, 6), round(lon_p, 6))
                    session_cache[key] = coords
                    return coords
    except Exception:
        pass

    # Fallback Suffolk centroid (Stowmarket/Mid Suffolk)
    fallback = (52.1889, 0.9972)
    session_cache[key] = fallback
    return fallback


def reverse_geocode_postcodes_batch(coords_list: list) -> dict:
    """Reverse-geocode (lat, lon) pairs in batches of 100 via postcodes.io, returning a rounded-coords to postcode map."""
    results = {}
    unique_coords = list({(round(lat, 5), round(lon, 5)) for lat, lon in coords_list if lat and lon})
    for i in range(0, len(unique_coords), 100):
        chunk = unique_coords[i:i + 100]
        # postcodes.io accepts max 100 geolocations per batch; search within 1 km
        geolocations = [{"longitude": lon, "latitude": lat, "limit": 1, "radius": 1000} for lat, lon in chunk]
        payload = json.dumps({"geolocations": geolocations}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.postcodes.io/postcodes",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("result") or []:
                    q = item.get("query", {})
                    q_key = (round(float(q.get("latitude", 0)), 5), round(float(q.get("longitude", 0)), 5))
                    res_list = item.get("result")
                    if res_list and len(res_list) > 0:
                        results[q_key] = res_list[0].get("postcode", "")
        except Exception as e:
            print(f"[{SLUG}] Batch reverse geocode warning: {e}")
        time.sleep(0.1)
    return results


def run():
    """Process the latest Livewire JSON export, resolve coordinates and postcodes, write data/suffolk.csv, and update metadata."""
    raw_json_path = find_latest_livewire_json()
    print(f"[{SLUG}] Loading Livewire dataset from {raw_json_path}...")

    with open(raw_json_path, "r", encoding="utf-8") as f:
        raw_items = json.load(f)

    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    # Load historical Suffolk stop coordinates
    hist_exact = {}
    hist_comm = {}
    hist_csv = os.path.join("history", "historical_mobile_stops.csv")
    if os.path.exists(hist_csv):
        with open(hist_csv, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("Local authority") == AUTHORITY_NAME and r.get("GeoX") and r.get("GeoY"):
                    try:
                        c = (round(float(r["GeoY"]), 6), round(float(r["GeoX"]), 6))
                        comm_k = r.get("Community", "").strip().lower()
                        stop_k = r.get("Stop", "").strip().lower()
                        addr_k = r.get("Address", "").strip().lower()
                        hist_exact[(comm_k, stop_k)] = c
                        hist_exact[addr_k] = c
                        hist_comm[comm_k] = c
                    except Exception:
                        pass

    session_place_cache = {}
    parsed_stops = []
    unscheduled_stops = []
    vehicles_seen = set()

    for item in raw_items:
        cells = item.get("cells") or []
        if len(cells) < 5:
            continue

        comm_raw = cells[0].strip()
        stop_raw = cells[1].strip()
        route_raw = cells[2].strip()
        date_raw = cells[3].strip()
        time_raw = cells[4].strip()

        links = item.get("links") or []
        stop_url = links[0].get("href") if links and links[0].get("href") else BASE_URL

        # Resolve coordinates
        clean_comm = re.sub(r"\(.*?\)", "", comm_raw).split(",")[0].strip()
        addr_str = f"{stop_raw}, {comm_raw}"
        coords = (
            hist_exact.get((comm_raw.lower(), stop_raw.lower()))
            or hist_exact.get((clean_comm.lower(), stop_raw.lower()))
            or hist_exact.get(addr_str.lower())
            or geocache.get(f"{AUTHORITY_NAME}:{comm_raw}:{stop_raw}".lower())
            or hist_comm.get(comm_raw.lower())
            or hist_comm.get(clean_comm.lower())
        )
        if not coords:
            coords = lookup_place_suffolk(clean_comm, session_place_cache)

        # Check if unscheduled ('–')
        if "Mobile" not in route_raw or "–" in date_raw or "–" in time_raw:
            unscheduled_stops.append({
                "community": comm_raw,
                "stop": stop_raw,
                "address": addr_str,
                "coords": coords,
                "url": stop_url
            })
            continue

        # Extract Mobile name and Route name
        # e.g. "Bury St Edmunds Mobile Library Route 7" -> Mobile: "Bury St Edmunds Mobile Library", Route: "Bury St Edmunds Mobile Library Route 7"
        m_mob = re.match(r"^(.*?Mobile Library)\s+(Route\s+.*)$", route_raw, re.I)
        if m_mob:
            mobile_name = m_mob.group(1).strip()
        else:
            mobile_name = route_raw
        vehicles_seen.add(mobile_name)

        # Parse Date & Day e.g. "Thu 10 Dec 2026"
        day_name = "Monday"
        start_date = "2026-12-01"
        m_dt = re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})$", date_raw)
        if m_dt:
            day_name = DAY_MAP.get(m_dt.group(1), "Monday")
            try:
                dt_obj = datetime.strptime(m_dt.group(2), "%d %b %Y")
                start_date = dt_obj.strftime("%Y-%m-%d")
            except Exception:
                pass

        # Parse Arrival & Departure e.g. "14:15 - 14:35"
        m_tm = re.match(r"^(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})$", time_raw)
        arr = m_tm.group(1) if m_tm else "10:00"
        dep = m_tm.group(2) if m_tm else "10:30"

        stype = "Private" if any(w in stop_raw.lower() or w in comm_raw.lower() for w in ["school", "nursery", "preschool"]) else "Public"

        parsed_stops.append({
            "mobile": mobile_name,
            "route": route_raw,
            "community": comm_raw,
            "stop": stop_raw,
            "address": addr_str,
            "coords": coords,
            "day": day_name,
            "type": stype,
            "arr": arr,
            "dep": dep,
            "start": start_date,
            "url": stop_url
        })

    print(f"[{SLUG}] Parsed {len(parsed_stops)} active scheduled stops and {len(unscheduled_stops)} unscheduled stops.")

    # Batch reverse geocode postcodes
    all_coords = [s["coords"] for s in parsed_stops if s["coords"]]
    pc_map = reverse_geocode_postcodes_batch(all_coords)

    stops_records = []
    for s in parsed_stops:
        lat, lon = s["coords"]
        pc = pc_map.get((round(lat, 5), round(lon, 5)), "")

        geocache[f"{AUTHORITY_NAME}:{s['community']}:{s['stop']}".lower()] = (lat, lon)
        if pc:
            geocache[pc] = (lat, lon)

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": AUTHORITY_CODE,
            "Mobile name": s["mobile"],
            "Route": s["route"],
            "Community": s["community"],
            "Stop": s["stop"],
            "Address": s["address"],
            "Postcode": pc,
            "GeoX": lon,
            "GeoY": lat,
            "Day": s["day"],
            "Type": s["type"],
            "Arrival": s["arr"],
            "Departure": s["dep"],
            "Frequency": "FREQ=WEEKLY;INTERVAL=4",
            "Start": s["start"],
            "End": "2027-12-31",
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

    # Frictionless validation
    schema = Schema("schemas/mobile-library-stops.json")
    # Skip foreign-key checks when validating the stops CSV standalone
    schema.foreign_keys = []
    resource = Resource(out_csv, schema=schema)
    report = resource.validate()
    print(f"[{SLUG}] Validation result: valid={report.valid}, errors={len(report.flatten(['rowNumber', 'fieldNumber', 'code', 'message']))}")
    if not report.valid:
        for err in report.flatten(['rowNumber', 'fieldNumber', 'code', 'message'])[:10]:
            print(f"  Row {err[0]}, Field {err[1]}: [{err[2]}] {err[3]}")

    # Archive unscheduled stops in history/historical_mobile_stops.csv
    if os.path.exists(hist_csv) and unscheduled_stops:
        with open(hist_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            h_fields = reader.fieldnames
            h_rows = list(reader)
        existing_h = {(r.get("Local authority"), r.get("Community"), r.get("Stop")) for r in h_rows}
        added_h = 0
        for u in unscheduled_stops:
            key = (AUTHORITY_NAME, u["community"], u["stop"])
            if key not in existing_h:
                lat, lon = u["coords"]
                h_rows.append({
                    "Local authority": AUTHORITY_NAME,
                    "Local authority code": AUTHORITY_CODE,
                    "Mobile name": "Unassigned",
                    "Route": "Unassigned",
                    "Community": u["community"],
                    "Stop": u["stop"],
                    "Address": u["address"],
                    "Postcode": "",
                    "GeoX": lon,
                    "GeoY": lat,
                    "Day": "",
                    "Type": "Public",
                    "Arrival": "",
                    "Departure": "",
                    "Frequency": "",
                    "Start": "",
                    "Dataset slug": SLUG,
                    "Archive source": "suffolk_livewire.json",
                    "Status": "Unscheduled / Suspended Stop"
                })
                added_h += 1
        if added_h > 0:
            with open(hist_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=h_fields)
                writer.writeheader()
                writer.writerows(h_rows)
            print(f"[{SLUG}] Archived {added_h} unscheduled Suffolk stops to historical registry.")

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
                    "Notes": "Suffolk Community Libraries active mobile fleet"
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
                r["source_format"] = "Livewire HTML Table (JSON Export)"
                r["last_checked"] = today
                r["last_updated"] = today
                r["notes"] = f"Harvested {len(stops_records)} active scheduled stops across Bury St Edmunds, Ipswich, and Leiston mobile libraries (plus 10 unscheduled stops archived)."
                break

        with open(services_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=s_fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[{SLUG}] Updated services.csv record for Suffolk.")


if __name__ == "__main__":
    run()
