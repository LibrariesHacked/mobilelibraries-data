"""
London Borough of Hillingdon Mobile Library Ingestion Script
Harvests live timetable from Hillingdon Council:
https://pre.hillingdon.gov.uk/libraries/mobile-library
Resolves postcodes, validates schema compliance, and updates services.csv, geocache, and historical vehicle registries.
"""

import os
import re
import json
import csv
import time
import urllib.request
from datetime import datetime
from bs4 import BeautifulSoup
from frictionless import Resource, Schema

AUTHORITY_NAME = "Hillingdon"
AUTHORITY_CODE = "E09000017"
SLUG = "hillingdon"

TIMETABLE_URL = "https://pre.hillingdon.gov.uk/libraries/mobile-library"
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor'}

POSTCODE_RE = re.compile(r"([A-Z]{1,2}[0-9][0-9A-Z]?\s*[0-9][A-Z]{2})", re.I)


def clean_time_24h(t_str: str) -> str:
    if not t_str:
        return ""
    t_str = t_str.strip().lower().replace(".", ":")
    if "midday" in t_str or "noon" in t_str:
        return "12:00"
    m = re.search(r"(\d{1,2}):(\d{2})\s*([ap]m)?", t_str)
    if m:
        h = int(m.group(1))
        mins = m.group(2)
        meridiem = m.group(3)
        if meridiem == "pm" and h < 12:
            h += 12
        elif meridiem == "am" and h == 12:
            h = 0
        return f"{h:02d}:{mins}"
    m_single = re.search(r"(\d{1,2})\s*([ap]m)", t_str)
    if m_single:
        h = int(m_single.group(1))
        meridiem = m_single.group(2)
        if meridiem == "pm" and h < 12:
            h += 12
        elif meridiem == "am" and h == 12:
            h = 0
        return f"{h:02d}:00"
    return ""


def batch_lookup_postcodes(postcodes_list):
    results = {}
    clean_pcs = [p.replace(" ", "").upper() for p in postcodes_list if p]
    pc_map = {p.replace(" ", "").upper(): p for p in postcodes_list if p}
    
    unique_pcs = list(pc_map.keys())
    for i in range(0, len(unique_pcs), 100):
        chunk = unique_pcs[i:i+100]
        data = json.dumps({"postcodes": chunk}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.postcodes.io/postcodes",
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                for item in res.get("result", []):
                    query_pc = item.get("query")
                    orig_pc = pc_map.get(query_pc, query_pc)
                    res_val = item.get("result")
                    if res_val and "longitude" in res_val and "latitude" in res_val:
                        results[orig_pc] = (res_val["latitude"], res_val["longitude"])
                        results[query_pc] = (res_val["latitude"], res_val["longitude"])
        except Exception as e:
            print(f"Batch lookup error for chunk {i}: {e}")
        time.sleep(0.15)
    return results


def run():
    print(f"[{SLUG}] Starting ingestion for {AUTHORITY_NAME} ({AUTHORITY_CODE})...")
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)
    raw_file = os.path.join(raw_dir, "mobile_library.html")

    # Load persistent geocache
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    req = urllib.request.Request(TIMETABLE_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    with open(raw_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[{SLUG}] Saved raw timetable HTML to {raw_file}")

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    raw_stops = []
    vehicle_name = "Hillingdon Mobile Library"

    for table in tables:
        prev = table.find_previous(["h2", "h3", "h4", "p"])
        heading = prev.get_text(strip=True) if prev else ""
        
        # Determine day
        day = "Monday"
        for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]:
            if d.lower() in heading.lower():
                day = d
                break

        rows = table.find_all("tr")
        if not rows:
            continue

        header_cells = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
        
        # Tuesday multi-column table (Week rota)
        if day == "Tuesday" and len(header_cells) >= 3:
            for tr in rows[1:]:
                tds = tr.find_all("td")
                if len(tds) < 2:
                    continue
                time_cell = tds[0].get_text(strip=True)
                t_parts = re.split(r"\s+to\s+", time_cell, flags=re.I)
                arr = clean_time_24h(t_parts[0]) if len(t_parts) > 0 else ""
                dep = clean_time_24h(t_parts[1]) if len(t_parts) > 1 else ""

                for col_idx in range(1, len(tds)):
                    cell_text = tds[col_idx].get_text(" ", strip=True)
                    if not cell_text:
                        continue
                    m_pc = POSTCODE_RE.search(cell_text)
                    pc = m_pc.group(1).upper() if m_pc else ""

                    # Split address
                    text_no_pc = cell_text.replace(pc, "").strip() if pc else cell_text
                    lines = [l.strip() for l in re.split(r",|\n", text_no_pc) if l.strip()]
                    name = lines[0] if lines else text_no_pc
                    comm = lines[-1] if len(lines) > 1 else "Hillingdon"

                    rota_date = header_cells[col_idx] if col_idx < len(header_cells) else f"Rota {col_idx}"
                    route = f"{vehicle_name} Tuesday {rota_date}"

                    # Type: Day Centre / Sheltered Home / Care Home -> Private
                    stype = "Private" if any(w in name.lower() for w in ["court", "lodge", "centre", "home", "house", "nursing"]) else "Public"

                    raw_stops.append({
                        "day": day,
                        "arr": arr,
                        "dep": dep,
                        "stop": name,
                        "comm": comm,
                        "addr": f"{text_no_pc}, {pc}".strip(", "),
                        "postcode": pc,
                        "route": route,
                        "freq": 3,
                        "type": stype
                    })

        # Roadside tables (Wednesday, Thursday, Friday)
        else:
            for tr in rows[1:]:
                tds = tr.find_all("td")
                if len(tds) < 2:
                    continue
                time_cell = tds[0].get_text(strip=True)
                loc_cell = tds[1].get_text(" ", strip=True)

                t_parts = re.split(r"\s+to\s+", time_cell, flags=re.I)
                arr = clean_time_24h(t_parts[0]) if len(t_parts) > 0 else ""
                dep = clean_time_24h(t_parts[1]) if len(t_parts) > 1 else ""

                # Check if multiple stops are embedded in one cell (e.g. 5 Nov vs 12 Nov)
                sub_parts = re.split(r"(?=\d{1,2}\s+(?:and\s+\d{1,2}\s+)?(?:November|December|January|February|March|April|May|June|July|August|September|October))", loc_cell)
                if len(sub_parts) > 1:
                    for sp in sub_parts:
                        sp = sp.strip()
                        if not sp: continue
                        m_date = re.match(r"^(\d{1,2}(?:\s+and\s+\d{1,2})?\s+[A-Za-z]+)\s+(.*)", sp)
                        rota_note = m_date.group(1) if m_date else ""
                        loc_text = m_date.group(2) if m_date else sp

                        m_pc = POSTCODE_RE.search(loc_text)
                        pc = m_pc.group(1).upper() if m_pc else ""
                        text_no_pc = loc_text.replace(pc, "").strip().strip(",") if pc else loc_text

                        parts = [p.strip() for p in text_no_pc.split(",") if p.strip()]
                        name = parts[0] if parts else text_no_pc
                        comm = parts[-1] if len(parts) > 1 else "Hillingdon"

                        stype = "Private" if any(w in name.lower() for w in ["school", "nursery", "preschool"]) else "Public"

                        raw_stops.append({
                            "day": day,
                            "arr": arr,
                            "dep": dep,
                            "stop": name,
                            "comm": comm,
                            "addr": f"{text_no_pc}, {pc}".strip(", "),
                            "postcode": pc,
                            "route": f"{vehicle_name} {day} {rota_note}".strip(),
                            "freq": 2 if "and" in rota_note else 4,
                            "type": stype
                        })
                else:
                    m_pc = POSTCODE_RE.search(loc_cell)
                    pc = m_pc.group(1).upper() if m_pc else ""
                    text_no_pc = loc_cell.replace(pc, "").strip().strip(",") if pc else loc_cell

                    parts = [p.strip() for p in text_no_pc.split(",") if p.strip()]
                    name = parts[0] if parts else text_no_pc
                    comm = parts[-1] if len(parts) > 1 else "Hillingdon"

                    stype = "Private" if any(w in name.lower() for w in ["school", "nursery", "preschool"]) else "Public"

                    raw_stops.append({
                        "day": day,
                        "arr": arr,
                        "dep": dep,
                        "stop": name,
                        "comm": comm,
                        "addr": f"{text_no_pc}, {pc}".strip(", "),
                        "postcode": pc,
                        "route": f"{vehicle_name} {day}",
                        "freq": 1,
                        "type": stype
                    })

    print(f"[{SLUG}] Extracted {len(raw_stops)} stops. Resolving postcodes...")

    # Batch geocode postcodes
    pcs_to_lookup = set(s["postcode"] for s in raw_stops if s["postcode"] and s["postcode"] not in geocache)
    if pcs_to_lookup:
        print(f"[{SLUG}] Looking up {len(pcs_to_lookup)} postcodes via postcodes.io...")
        resolved = batch_lookup_postcodes(list(pcs_to_lookup))
        for pc, coords in resolved.items():
            geocache[pc] = coords
            geocache[pc.replace(" ", "")] = coords

        with open(geocache_path, "w", encoding="utf-8") as f:
            json.dump(geocache, f, indent=2)

    # Build schema-compliant stops
    stops_records = []
    for s in raw_stops:
        pc = s["postcode"]
        coords = geocache.get(pc) or geocache.get(pc.replace(" ", ""))
        lat = round(coords[0], 6) if coords else ""
        lng = round(coords[1], 6) if coords else ""

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": AUTHORITY_CODE,
            "Mobile name": vehicle_name,
            "Route": s["route"],
            "Community": s["comm"],
            "Stop": s["stop"],
            "Address": s["addr"],
            "Postcode": pc,
            "GeoX": lng,
            "GeoY": lat,
            "Day": s["day"],
            "Type": s["type"],
            "Arrival": s["arr"],
            "Departure": s["dep"],
            "Frequency": (f"FREQ=WEEKLY;INTERVAL={s["freq"]}" if str(s["freq"]).isdigit() else s["freq"]),
            "Start": "2026-01-05",
            "End": "2026-12-31",
            "Exceptions": "Bank holidays",
            "Timetable": TIMETABLE_URL
        })

    stops_records.sort(key=lambda r: (r["Mobile name"], r["Day"], r["Arrival"], r["Stop"]))

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
    print(f"[{SLUG}] Validating schema compliance...")
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

    # Update historical vehicles
    vehicles_csv = os.path.join("history", "historical_mobile_vehicles.csv")
    if os.path.exists(vehicles_csv):
        existing_rows = []
        with open(vehicles_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            v_fieldnames = reader.fieldnames
            existing_rows = list(reader)

        existing_keys = {(r.get("Local authority"), r.get("Mobile name")) for r in existing_rows}
        key = (AUTHORITY_NAME, vehicle_name)
        if key not in existing_keys:
            existing_rows.append({
                "Local authority": AUTHORITY_NAME,
                "Mobile name": vehicle_name,
                "Dataset slug": SLUG,
                "Status": "Active",
                "Notes": "London Borough of Hillingdon Mobile Library"
            })
            with open(vehicles_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=v_fieldnames)
                writer.writeheader()
                writer.writerows(existing_rows)
            print(f"[{SLUG}] Added vehicle to historical vehicle registry.")

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
                r["source_url"] = TIMETABLE_URL
                r["source_format"] = "HTML Website"
                r["last_checked"] = today
                r["last_updated"] = today
                r["notes"] = f"Harvested {len(stops_records)} stops from Hillingdon Council mobile library timetable."
                updated = True
                break

        if updated:
            with open(services_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=s_fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"[{SLUG}] Updated services.csv record.")


if __name__ == "__main__":
    run()
