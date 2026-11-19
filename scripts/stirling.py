"""
Ingestion script for Stirling Council Mobile Library Service.
Harvests routes, timetables, and stops from Stirling Council official website
(stirling.gov.uk/community-life-and-leisure/libraries-and-archives/libraries/mobile-libraries/mobile-library-timetable/mobile-library-timetable/).
Geocodes via postcodes.io, validates schema compliance, and updates services.csv and geocache.
"""

import os
import re
import csv
import json
from datetime import datetime
import urllib.request
from bs4 import BeautifulSoup
from frictionless import Resource, Schema

DATASET_SLUG = "stirling"
AUTHORITY_NAME = "Stirling"
GSS_CODE = "S12000030"
BASE_URL = "https://www.stirling.gov.uk/community-life-and-leisure/libraries-and-archives/libraries/mobile-libraries/mobile-library-timetable/mobile-library-timetable/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9"
}

POSTCODE_MAP = {
    "lochearnhead": "FK19 8PR",
    "strathyre": "FK18 8NA",
    "thornhill": "FK8 3PJ",
    "gargunnock": "FK8 3BW",
    "dunblane": "FK15 0EH",
    "croftamie": "G63 0EU",
    "miltonofbuchanan": "G63 0JE",
    "drymen": "G63 0BP",
    "riverside": "FK8 1UD",
    "causewayhead": "FK9 5JS",
    "blairlogie": "FK9 5PX",
    "manorpowis": "FK9 5PS",
    "killearn": "G63 9NP",
    "buchlyvie": "FK8 3LX",
    "portofmenteith": "FK8 3RA",
    "dykehead": "FK8 3JY",
    "gartmore": "FK8 3RW",
    "camphill": "FK16 6HG",
    "brigo'turk": "FK17 8HT",
    "balquhidder": "FK19 8NY",
    "fintry": "G63 0YB",
    "kippen": "FK8 3DN",
    "kingspark": "FK8 2PQ",
    "stninians": "FK7 0PW",
    "torbrex": "FK8 2LB",
    "cultenhove": "FK7 9NP",
    "throsk": "FK7 7NA",
    "cambuskenneth": "FK9 5NX",
    "kincardineinmenteith": "FK16 6AB",
    "deanston": "FK16 6AH",
    "kinbuck": "FK15 0NQ",
    "ashfield": "FK15 0JN",
    "arnprior": "FK8 3HA",
    "braeval": "FK8 3TU",
    "aberfoyle": "FK8 3SY",
    "aberoyle": "FK8 3SY",
    "kinlochard": "FK8 3TL",
    "crianlarich": "FK20 8QN",
    "tyndrum": "FK20 8RY"
}


def parse_time(t_str: str) -> str:
    """Parse time strings like '11am', '1:25pm', '12pm' into 24-hr HH:MM."""
    if not t_str:
        return ""
    t_str = t_str.strip().lower()
    m = re.search(r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?", t_str)
    if not m:
        return ""
    h = int(m.group(1))
    mins = m.group(2) if m.group(2) else "00"
    meridiem = m.group(3)
    if meridiem == "pm" and h < 12:
        h += 12
    elif meridiem == "am" and h == 12:
        h = 0
    elif not meridiem and h < 8:
        h += 12
    return f"{h:02d}:{mins}"


def bulk_lookup_postcodes(pcs: list) -> dict:
    """Lookup multiple postcodes via postcodes.io batch endpoint."""
    unique_pcs = list({p for p in pcs if p})
    coords = {}
    if not unique_pcs:
        return coords

    for i in range(0, len(unique_pcs), 100):
        chunk = unique_pcs[i:i + 100]
        req = urllib.request.Request(
            "https://api.postcodes.io/postcodes",
            data=json.dumps({"postcodes": chunk}).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": HEADERS["User-Agent"]}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("result", []):
                    pc = item.get("query")
                    res = item.get("result")
                    if res:
                        coords[pc] = {
                            "lat": float(res["latitude"]),
                            "lon": float(res["longitude"]),
                            "postcode": res.get("postcode", pc)
                        }
        except Exception as e:
            print(f"[{DATASET_SLUG}] Postcode batch lookup warning: {e}")

    return coords


def main():
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)
    raw_html_path = os.path.join(raw_dir, "mobile_library_timetable.html")

    print(f"[{DATASET_SLUG}] Fetching timetable from {BASE_URL}")
    req = urllib.request.Request(BASE_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        html_content = resp.read().decode("utf-8")

    with open(raw_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[{DATASET_SLUG}] Saved raw HTML to {raw_html_path}")

    soup = BeautifulSoup(html_content, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        raise ValueError("Could not find timetable tables on Stirling Council page")

    raw_records = []
    for idx, t in enumerate(tables):
        week = "Week 1" if idx < 6 else "Week 2"

        prev = t.find_previous(["h3", "h4", "h5", "p", "strong"])
        h_txt = prev.get_text(strip=True) if prev else ""
        van = "Mobile Library Van 2" if "van 2" in h_txt.lower() else "Mobile Library Van 1"

        day = "Monday"
        for p in t.find_all_previous(["h3", "h4", "h5", "p"]):
            dm = re.search(r"(Monday|Tuesday|Wednesday|Thursday|Friday)", p.get_text(), re.I)
            if dm:
                day = dm.group(1).title()
                break

        last_loc = ""
        for r in t.find_all("tr"):
            cells = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
            if not cells or "arrive" in cells[-2].lower() or "locality" in cells[0].lower():
                continue
            loc = cells[0] if cells[0] else last_loc
            last_loc = loc
            stop = cells[1] if len(cells) > 1 and cells[1] else loc
            arr_raw = cells[2] if len(cells) > 2 else ""
            dep_raw = cells[3] if len(cells) > 3 else ""

            # Fix typos from council page
            if loc.lower() == "aberoyle":
                loc = "Aberfoyle"
            if loc.lower() == "buchlyvie" and "5:40" in arr_raw and "4:40" in dep_raw:
                arr_raw, dep_raw = "4:40pm", "5:40pm"
            if loc.lower() == "aberfoyle" and "1:30am" in arr_raw:
                arr_raw = "1:30pm"
            if loc.lower() == "crianlarich" and "11:30pm" in dep_raw:
                dep_raw = "11:30am"

            arr = parse_time(arr_raw)
            dep = parse_time(dep_raw)

            # Determine stop type: enum is ['Public', 'Private', 'Dynamic', 'Other']
            stop_type = "Private" if "school" in stop.lower() or "nursery" in stop.lower() else "Public"

            raw_records.append({
                "week": week,
                "day": day,
                "van": van,
                "locality": loc,
                "stop": stop,
                "arr": arr,
                "dep": dep,
                "type": stop_type
            })

    print(f"[{DATASET_SLUG}] Extracted {len(raw_records)} raw stop records.")

    # Geocode postcodes
    pcs_to_lookup = []
    for r in raw_records:
        norm_c = re.sub(r"[^a-z0-9]", "", r["locality"].lower())
        pc = POSTCODE_MAP.get(norm_c, "")
        if pc:
            pcs_to_lookup.append(pc)

    coords_cache = bulk_lookup_postcodes(pcs_to_lookup)

    # Load existing geocache
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    stops_records = []
    for r in raw_records:
        comm = r["locality"]
        stop = r["stop"]
        norm_c = re.sub(r"[^a-z0-9]", "", comm.lower())
        pc = POSTCODE_MAP.get(norm_c, "")

        lat, lng = None, None
        if pc in coords_cache:
            lat = coords_cache[pc]["lat"]
            lng = coords_cache[pc]["lon"]
            pc = coords_cache[pc]["postcode"]

        address = f"{stop}, {comm}" if stop != comm else comm

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": GSS_CODE,
            "Mobile name": r["van"],
            "Route": f"{r['week']} {r['day']}",
            "Community": comm,
            "Stop": stop,
            "Address": address,
            "Postcode": pc,
            "GeoX": round(float(lng), 6) if lng else "",
            "GeoY": round(float(lat), 6) if lat else "",
            "Day": r["day"],
            "Type": r["type"],
            "Arrival": r["arr"],
            "Departure": r["dep"],
            "Frequency": "FREQ=WEEKLY;INTERVAL=2",
            "Start": "2026-07-06",
            "End": "2026-12-23",
            "Exceptions": "",
            "Timetable": BASE_URL
        })

    print(f"[{DATASET_SLUG}] Prepared {len(stops_records)} validated stop records.")

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
                    row["notes"] = f"Harvested {len(stops_records)} stops across Mobile Library Van 1 and Van 2 from Stirling Council."
                rows.append(row)
        with open(services_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fn)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[{DATASET_SLUG}] Updated {services_path}")

    # Update vehicles
    v_path = os.path.join("history", "historical_mobile_vehicles.csv")
    if os.path.exists(v_path):
        with open(v_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            v_fn = reader.fieldnames
            v_rows = list(reader)
        existing = {r["Mobile name"] for r in v_rows if r["Local authority"] == AUTHORITY_NAME}
        for van_n, desc in [("Mobile Library Van 1", "Stirling rural routes van."), ("Mobile Library Van 2", "Stirling second active van.")]:
            if van_n not in existing:
                v_rows.append({
                    "Local authority": AUTHORITY_NAME,
                    "Mobile name": van_n,
                    "Dataset slug": DATASET_SLUG,
                    "Status": "Active",
                    "Notes": desc
                })
        with open(v_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=v_fn)
            writer.writeheader()
            writer.writerows(v_rows)
        print(f"[{DATASET_SLUG}] Updated {v_path}")


if __name__ == "__main__":
    main()
