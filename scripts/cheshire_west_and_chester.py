"""
Ingestion script for Cheshire West and Chester Mobile Library Service.
Harvests routes, timetables, and stops from Cheshire West and Chester Council official website
(cheshirewestandchester.gov.uk/residents/libraries/find-a-library/mobile-library-service).
Geocodes via postcodes.io, validates schema compliance, and updates services.csv and geocache.
"""

from _common import bulk_lookup_postcodes
import os
import re
import csv
import json
from datetime import datetime
import urllib.request
from bs4 import BeautifulSoup
from frictionless import Resource, Schema

DATASET_SLUG = "cheshire_west_and_chester"
AUTHORITY_NAME = "Cheshire West and Chester"
GSS_CODE = "E06000050"
BASE_URL = "https://www.cheshirewestandchester.gov.uk/residents/libraries/find-a-library/mobile-library-service"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9"
}


def parse_time_single(t_str: str) -> str:
    """Format single time string into 24-hr HH:MM."""
    if not t_str:
        return ""
    t_str = t_str.strip().lower()
    m = re.search(r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?", t_str)
    if not m:
        return ""
    h = int(m.group(1))
    mins = m.group(2) if m.group(2) else "00"
    mer = m.group(3)
    if mer == "pm" and h < 12:
        h += 12
    elif mer == "am" and h == 12:
        h = 0
    elif not mer and h < 8:
        # Assume hours < 8 without am/pm are afternoon (mobile library hours)
        h += 12
    return f"{h:02d}:{mins}"


def parse_range(r_str: str) -> tuple:
    """Split time string like '9.25am - 9.40am' into (arrival, departure)."""
    parts = re.split(r"\s*-\s*", r_str)
    arr = parse_time_single(parts[0]) if len(parts) > 0 else ""
    dep = parse_time_single(parts[1]) if len(parts) > 1 else ""
    return arr, dep




def main():
    """Fetch Cheshire West and Chester timetables, geocode postcodes, write data/cheshire_west_and_chester.csv, and validate.

    Also updates the shared geocache, services.csv, and historical_mobile_vehicles.csv.
    """
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)
    raw_html_path = os.path.join(raw_dir, "mobile_library_service.html")

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
        raise ValueError("Could not find route tables on Cheshire West and Chester page")

    raw_records = []
    pcs_to_lookup = []

    for t in tables:
        prev_day = t.find_previous(["h3", "h4"])
        day_txt = prev_day.get_text(strip=True) if prev_day else "Monday"

        prev_week = t.find_previous(["h2"])
        week_txt = prev_week.get_text(strip=True) if prev_week else "Week one"

        for tr in t.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 3:
                comm = tds[0].get_text(strip=True)
                if "village" in comm.lower():
                    # Skip table header rows
                    continue

                # Multiple stops/times in one cell use <p> tags; pair them, falling back to last entry
                p_stops = [p.get_text(strip=True) for p in tds[1].find_all("p")] or [tds[1].get_text(strip=True)]
                p_times = [p.get_text(strip=True) for p in tds[2].find_all("p")] or [tds[2].get_text(strip=True)]

                for i in range(max(len(p_stops), len(p_times))):
                    st_text = p_stops[i] if i < len(p_stops) else p_stops[-1]
                    tm_text = p_times[i] if i < len(p_times) else p_times[-1]

                    # Match UK postcode embedded in stop text
                    m_pc = re.search(r"([A-Z]{1,2}\d[A-Z0-9]?\s*\d[A-Z]{2})", st_text)
                    pc = m_pc.group(1).upper() if m_pc else ""

                    clean_stop = re.sub(r",?\s*[A-Z]{1,2}\d[A-Z0-9]?\s*\d[A-Z]{2}", "", st_text).strip(", ")

                    arr, dep = parse_range(tm_text)
                    if arr and dep:
                        raw_records.append({
                            "week": week_txt,
                            "day": day_txt,
                            "community": comm,
                            "stop": clean_stop,
                            "postcode": pc,
                            "arrival": arr,
                            "departure": dep
                        })
                        if pc:
                            pcs_to_lookup.append(pc)

    print(f"[{DATASET_SLUG}] Extracted {len(raw_records)} raw stop records.")

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
        comm = r["community"]
        stop = r["stop"]
        pc = r["postcode"]

        lat, lng = None, None
        if pc in coords_cache:
            lat = coords_cache[pc]["lat"]
            lng = coords_cache[pc]["lon"]
            pc = coords_cache[pc]["postcode"]

        address = f"{stop}, {comm}" if stop != comm else comm

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": GSS_CODE,
            "Mobile name": "Electric Mobile Library",
            "Route": f"{r['week']} {r['day']}",
            "Community": comm,
            "Stop": stop,
            "Address": address,
            "Postcode": pc,
            "GeoX": round(float(lng), 6) if lng else "",
            "GeoY": round(float(lat), 6) if lat else "",
            "Day": r["day"],
            "Type": "Public",
            "Arrival": r["arrival"],
            "Departure": r["departure"],
            "Frequency": "FREQ=WEEKLY;INTERVAL=3",
            "Start": "2026-01-05",
            "End": "2026-12-23",
            "Exceptions": "Bank Holidays and weekends",
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
    # Disable foreign-key checks for standalone CSV validation
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
                    row["notes"] = f"Harvested {len(stops_records)} stops across 3-week rota from Cheshire West and Chester Council."
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
        if "Electric Mobile Library" not in existing:
            v_rows.append({
                "Local authority": AUTHORITY_NAME,
                "Mobile name": "Electric Mobile Library",
                "Dataset slug": DATASET_SLUG,
                "Status": "Active",
                "Notes": "Cheshire West and Chester custom zero-emission electric mobile library van."
            })
            with open(v_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=v_fn)
                writer.writeheader()
                writer.writerows(v_rows)
            print(f"[{DATASET_SLUG}] Updated {v_path}")


if __name__ == "__main__":
    main()
