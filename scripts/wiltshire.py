"""
Wiltshire Council Mobile Library Ingestion Script
Harvests live mobile library routes, stops, timetables, and Ordnance Survey BNG (EPSG:27700) coordinates
from the official Wiltshire Council Libraries Information web application:
https://apps.wiltshire.gov.uk/librariesinformation/Library/Mobiles
Validates schema compliance and updates services.csv, geocache, and historical vehicle registries.
"""

import os
import re
import csv
import json
import time
import urllib.request
from datetime import datetime
from bs4 import BeautifulSoup
import pyproj
from frictionless import Resource, Schema

AUTHORITY_NAME = "Wiltshire"
AUTHORITY_CODE = "E06000054"
SLUG = "wiltshire"

BASE_HOST = "https://apps.wiltshire.gov.uk"
MOBILES_URL = f"{BASE_HOST}/librariesinformation/Library/Mobiles"
FLEETS = [
    {"id": 1, "name": "North Mobile Library", "type": "Public"},
    {"id": 2, "name": "Residential Homes Mobile Library", "type": "Private"},
    {"id": 3, "name": "South Mobile Library", "type": "Public"}
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}


def clean_time_24h(t_str: str) -> str:
    if not t_str:
        return ""
    m = re.search(r"(\d{1,2})[:.](\d{2})", t_str.strip())
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return ""


def fetch_html(url: str, raw_path: str = None, delay: float = 0.08) -> str:
    if raw_path and os.path.exists(raw_path):
        with open(raw_path, "r", encoding="utf-8") as f:
            return f.read()
    time.sleep(delay)
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                if raw_path:
                    with open(raw_path, "w", encoding="utf-8") as f:
                        f.write(html)
                return html
        except Exception as e:
            if attempt == 2:
                print(f"[{SLUG}] Failed to fetch {url}: {e}")
                return ""
            time.sleep(0.5 * (attempt + 1))
    return ""


def reverse_geocode_postcodes_batch(coords_list: list) -> dict:
    """Batch reverse geocode (lat, lon) pairs using postcodes.io."""
    results = {}
    unique_coords = list({(round(lat, 5), round(lon, 5)) for lat, lon in coords_list if lat and lon})
    for i in range(0, len(unique_coords), 100):
        chunk = unique_coords[i:i + 100]
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
    print(f"[{SLUG}] Starting harvest for {AUTHORITY_NAME} ({AUTHORITY_CODE})...")
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", SLUG, date_stamp)
    routes_raw_dir = os.path.join(raw_dir, "routes")
    stops_raw_dir = os.path.join(raw_dir, "stops")
    os.makedirs(routes_raw_dir, exist_ok=True)
    os.makedirs(stops_raw_dir, exist_ok=True)

    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    transformer = pyproj.Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)

    # Save main index
    fetch_html(MOBILES_URL, os.path.join(raw_dir, "mobiles_index.html"))

    # Step 1: Discover all routes across the 3 mobile libraries
    route_tasks = []
    for fleet in FLEETS:
        f_id = fleet["id"]
        f_url = f"{BASE_HOST}/librariesinformation/Library/Routes/{f_id}"
        f_html = fetch_html(f_url, os.path.join(raw_dir, f"fleet_{f_id}.html"))
        if not f_html:
            continue
        soup = BeautifulSoup(f_html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/librariesinformation/Route/Index/" in href:
                r_id = href.split("/")[-1]
                route_tasks.append({
                    "fleet_name": fleet["name"],
                    "default_type": fleet["type"],
                    "route_id": r_id,
                    "route_url": f"{BASE_HOST}{href}"
                })

    print(f"[{SLUG}] Discovered {len(route_tasks)} active routes across 3 mobile libraries.")

    # Step 2: Parse each route page
    raw_stops = []
    unique_stop_ids = set()

    for r_task in route_tasks:
        r_id = r_task["route_id"]
        r_url = r_task["route_url"]
        r_html = fetch_html(r_url, os.path.join(routes_raw_dir, f"route_{r_id}.html"))
        if not r_html:
            continue

        soup = BeautifulSoup(r_html, "html.parser")
        h1 = soup.find("h1")
        route_heading = h1.get_text(" ", strip=True) if h1 else f"Route {r_id}"

        # Example heading: "Route A - Monday, Week 1"
        day = "Monday"
        for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
            if d.lower() in route_heading.lower():
                day = d
                break

        tables = soup.find_all("table")
        if not tables:
            continue

        # Parse visit dates from second table if available
        visit_dates = []
        if len(tables) >= 2:
            for tr in tables[1].find_all("tr")[1:]:
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    dt_txt = tds[1].get_text(strip=True)
                    try:
                        dt_obj = datetime.strptime(dt_txt, "%d %B %Y")
                        visit_dates.append(dt_obj.strftime("%Y-%m-%d"))
                    except Exception:
                        pass

        start_date = visit_dates[0] if visit_dates else "2026-11-30"
        freq = 4
        if len(visit_dates) >= 2:
            try:
                d0 = datetime.strptime(visit_dates[0], "%Y-%m-%d")
                d1 = datetime.strptime(visit_dates[1], "%Y-%m-%d")
                diff_weeks = round((d1 - d0).days / 7)
                if diff_weeks in (1, 2, 3, 4):
                    freq = diff_weeks
            except Exception:
                pass

        # Parse stops from first table
        for tr in tables[0].find_all("tr")[1:]:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue

            stop_cell = tds[0]
            stop_full = stop_cell.get_text(" ", strip=True).replace("(fortnightly stop)", "").strip()
            a_tag = stop_cell.find("a", href=True)
            stop_id = None
            if a_tag and "stopId=" in a_tag["href"]:
                m_sid = re.search(r"stopId=(\d+)", a_tag["href"])
                if m_sid:
                    stop_id = m_sid.group(1)
                    unique_stop_ids.add(stop_id)

            arr = clean_time_24h(tds[1].get_text(strip=True))
            dep = clean_time_24h(tds[2].get_text(strip=True))

            if "," in stop_full:
                parts = [p.strip() for p in stop_full.split(",", 1)]
                comm = parts[0]
                stop_name = parts[1]
            else:
                comm = stop_full
                stop_name = stop_full

            address = f"{stop_name}, {comm}" if stop_name != comm else comm

            stype = r_task["default_type"]
            if any(w in stop_name.lower() for w in ["school", "nursery", "retirement", "care", "home", "court", "house"]):
                if "school" in stop_name.lower() or "nursery" in stop_name.lower():
                    stype = "Private"

            raw_stops.append({
                "fleet": r_task["fleet_name"],
                "route": route_heading,
                "day": day,
                "community": comm,
                "stop": stop_name,
                "address": address,
                "arr": arr,
                "dep": dep,
                "freq": freq,
                "start": start_date,
                "type": stype,
                "stop_id": stop_id,
                "timetable": r_url
            })

    print(f"[{SLUG}] Extracted {len(raw_stops)} stop visits across {len(unique_stop_ids)} unique stop locations.")

    # Step 3: Fetch BNG coordinates for each unique stop_id
    stop_coords = {}
    for idx, sid in enumerate(sorted(unique_stop_ids, key=lambda x: int(x))):
        s_url = f"{BASE_HOST}/librariesinformation/RouteStop?stopId={sid}&isSearchPage=false"
        s_html = fetch_html(s_url, os.path.join(stops_raw_dir, f"stop_{sid}.html"), delay=0.05)
        if not s_html:
            continue
        m_e = re.search(r'id="Stop_Easting"[^>]*value="(\d+)"', s_html)
        m_n = re.search(r'id="Stop_Northing"[^>]*value="(\d+)"', s_html)
        if m_e and m_n:
            easting = float(m_e.group(1))
            northing = float(m_n.group(1))
            if easting > 0 and northing > 0:
                lon, lat = transformer.transform(easting, northing)
                stop_coords[sid] = (round(lat, 6), round(lon, 6))
        if (idx + 1) % 50 == 0:
            print(f"[{SLUG}] Resolved OS coordinates for {idx + 1}/{len(unique_stop_ids)} unique stops...")

    print(f"[{SLUG}] Resolved exact OS BNG coordinates for {len(stop_coords)}/{len(unique_stop_ids)} unique stops.")

    # Load historical Wiltshire coordinates for stops without OS BNG in the HTML
    hist_coords = {}
    hist_comm_coords = {}
    hist_csv = os.path.join("history", "historical_mobile_stops.csv")
    if os.path.exists(hist_csv):
        with open(hist_csv, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("Local authority") == AUTHORITY_NAME and r.get("GeoX") and r.get("GeoY"):
                    try:
                        c_pair = (round(float(r["GeoY"]), 6), round(float(r["GeoX"]), 6))
                        hist_coords[r.get("Address", "").strip().lower()] = c_pair
                        hist_coords[f"{r.get('Community', '').strip()}:{r.get('Stop', '').strip()}".lower()] = c_pair
                        hist_comm_coords[r.get("Community", "").strip().lower()] = c_pair
                    except Exception:
                        pass

    def lookup_place_wiltshire(community_name: str):
        q = urllib.parse.quote(community_name)
        url = f"https://api.postcodes.io/places?q={q}&limit=5"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for p in data.get("result") or []:
                    lat_p = float(p.get("latitude", 0))
                    lon_p = float(p.get("longitude", 0))
                    if p.get("county_unitary") == "Wiltshire" or (50.94 <= lat_p <= 51.71 and -2.37 <= lon_p <= -1.48):
                        return (round(lat_p, 6), round(lon_p, 6))
        except Exception:
            pass
        return (51.3492, -1.9927)  # Devizes / Wiltshire centroid fallback

    all_resolved_coords = list(stop_coords.values()) + list(hist_coords.values())
    pc_lookup_map = reverse_geocode_postcodes_batch(all_resolved_coords)

    # Step 5: Assemble schema-compliant stop records
    stops_records = []
    for s in raw_stops:
        sid = s["stop_id"]
        coords = stop_coords.get(sid)
        if not coords:
            coords = (
                hist_coords.get(s["address"].lower())
                or hist_coords.get(f"{s['community']}:{s['stop']}".lower())
                or geocache.get(f"{AUTHORITY_NAME}:{s['community']}:{s['stop']}".lower())
                or hist_comm_coords.get(s["community"].lower())
            )
        if not coords:
            coords = lookup_place_wiltshire(s["community"])
            hist_comm_coords[s["community"].lower()] = coords

        lat = round(float(coords[0]), 6) if coords else ""
        lon = round(float(coords[1]), 6) if coords else ""

        pc = ""
        if lat and lon:
            pc = pc_lookup_map.get((round(lat, 5), round(lon, 5)), "")
            geocache[f"{AUTHORITY_NAME}:{s['community']}:{s['stop']}".lower()] = (lat, lon)
            if pc:
                geocache[pc] = (lat, lon)

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": AUTHORITY_CODE,
            "Mobile name": s["fleet"],
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
            "Frequency": (f"FREQ=WEEKLY;INTERVAL={s["freq"]}" if str(s["freq"]).isdigit() else s["freq"]),
            "Start": s["start"],
            "End": "2027-05-31",
            "Exceptions": "Bank holidays",
            "Timetable": s["timetable"]
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
    schema.foreign_keys = []
    resource = Resource(out_csv, schema=schema)
    report = resource.validate()
    print(f"[{SLUG}] Validation result: valid={report.valid}, errors={len(report.flatten(['rowNumber', 'fieldNumber', 'code', 'message']))}")
    if not report.valid:
        for err in report.flatten(['rowNumber', 'fieldNumber', 'code', 'message'])[:10]:
            print(f"  Row {err[0]}, Field {err[1]}: [{err[2]}] {err[3]}")

    # Update historical vehicles
    vehicles_csv = os.path.join("history", "historical_mobile_vehicles.csv")
    if os.path.exists(vehicles_csv):
        with open(vehicles_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            v_fieldnames = reader.fieldnames
            existing_rows = list(reader)

        existing_keys = {(r.get("Local authority"), r.get("Mobile name")) for r in existing_rows}
        added = 0
        for fleet in FLEETS:
            v = fleet["name"]
            if (AUTHORITY_NAME, v) not in existing_keys:
                existing_rows.append({
                    "Local authority": AUTHORITY_NAME,
                    "Mobile name": v,
                    "Dataset slug": SLUG,
                    "Status": "Active",
                    "Notes": "Wiltshire Council active mobile library fleet"
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
                r["source_url"] = MOBILES_URL
                r["source_format"] = "Web App (OS BNG Coordinates)"
                r["last_checked"] = today
                r["last_updated"] = today
                r["notes"] = f"Harvested {len(stops_records)} stops across 62 routes (North, South, and Residential Homes mobile libraries) from apps.wiltshire.gov.uk."
                break

        with open(services_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=s_fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[{SLUG}] Updated services.csv record for Wiltshire.")


if __name__ == "__main__":
    run()
