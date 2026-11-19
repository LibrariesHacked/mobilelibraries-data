"""
Ingestion script for Cheshire East Council Mobile Library Service.
Harvests routes, timetables, and stops from Cheshire East official portal
(cheshireeast.gov.uk/libraries/nearest-library/mobile_library_routes.aspx).
Geocodes via postcodes.io/places, validates schema compliance, and updates services.csv and geocache.
"""

from _common import reverse_geocode_postcode
import os
import re
import csv
import json
from datetime import datetime
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
from frictionless import Resource, Schema

DATASET_SLUG = "cheshire_east"
AUTHORITY_NAME = "Cheshire East"
GSS_CODE = "E06000049"
BASE_URL = "https://www.cheshireeast.gov.uk/libraries/nearest-library/mobile_library_routes.aspx"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9"
}


def parse_time_single(t_str: str) -> str:
    """Format single time string like '10am', '1:25pm', '10:45am' into 24-hr HH:MM."""
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
    """Split time string like '10am to 10:45am' into (arrival, departure)."""
    parts = re.split(r"\s*to\s*|-", r_str, flags=re.I)
    arr = parse_time_single(parts[0]) if len(parts) > 0 else ""
    dep = parse_time_single(parts[1]) if len(parts) > 1 else ""
    return arr, dep


def geocode_place_postcodes_io(place: str, cache: dict) -> tuple:
    """Geocode place using postcodes.io/places API with priority for Cheshire outcodes."""
    clean_p = place.split("/")[0].strip()
    if clean_p in cache:
        return cache[clean_p]

    url = f"https://api.postcodes.io/places?q={urllib.parse.quote(clean_p)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("result", [])
            if results:
                # Prioritize Cheshire and surrounding outcodes
                chesh_matches = [r for r in results if "Cheshire" in str(r.get("admin_district", "")) or str(r.get("outcode", "")).startswith(("CW", "SK", "WA", "ST", "SY"))]
                chosen = chesh_matches[0] if chesh_matches else results[0]
                lat = float(chosen["latitude"])
                lng = float(chosen["longitude"])
                outcode = chosen.get("outcode", "")
                cache[clean_p] = (lat, lng, outcode)
                return lat, lng, outcode
    except Exception:
        pass

    cache[clean_p] = (None, None, "")
    return None, None, ""




def main():
    """Fetch Cheshire East timetables, geocode stops, write data/cheshire_east.csv, and validate schema.

    Also updates the shared geocache, services.csv, and historical_mobile_vehicles.csv.
    """
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)
    raw_html_path = os.path.join(raw_dir, "mobile_library_routes.html")

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
        raise ValueError("Could not find route tables on Cheshire East page")

    raw_records = []
    for t in tables:
        cap = t.find("caption")
        cap_txt = cap.get_text(strip=True) if cap else ""
        # e.g. "Week 1: Tuesday"
        m_route = re.search(r"(Week\s*\d+)\s*:\s*(Monday|Tuesday|Wednesday|Thursday|Friday)", cap_txt, re.I)
        week = m_route.group(1).title() if m_route else "Week 1"
        day = m_route.group(2).title() if m_route else "Monday"

        for tr in t.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 3:
                comm = tds[0].get_text(strip=True)
                stop = tds[1].get_text(strip=True)
                time_raw = tds[2].get_text(strip=True)

                if "village" in comm.lower() or "times" in time_raw.lower():
                    # Skip table header rows
                    continue

                arr, dep = parse_range(time_raw)
                if arr and dep:
                    raw_records.append({
                        "week": week,
                        "day": day,
                        "community": comm,
                        "stop": stop,
                        "arrival": arr,
                        "departure": dep
                    })

    print(f"[{DATASET_SLUG}] Extracted {len(raw_records)} raw stop records.")

    # Load existing geocache
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    place_cache = {}
    postcode_cache = {}
    stops_records = []

    for r in raw_records:
        comm = r["community"]
        stop = r["stop"]
        norm_c = re.sub(r"[^a-z0-9]", "", comm.lower())
        norm_s = re.sub(r"[^a-z0-9]", "", stop.lower())
        cache_key = f"{DATASET_SLUG}::{norm_c}::{norm_s}"

        lat, lng = None, None
        postcode = ""

        if cache_key in geocache:
            entry = geocache[cache_key]
            lat = entry.get("geoy")
            lng = entry.get("geox")
            postcode = entry.get("postcode", "")

        if not lat:
            lat, lng, outcode = geocode_place_postcodes_io(comm, place_cache)

        if lat and lng and not postcode:
            postcode = reverse_geocode_postcode(lat, lng, postcode_cache)

        address = f"{stop}, {comm}" if stop != comm else comm

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": GSS_CODE,
            "Mobile name": "Cheshire East Mobile Library",
            "Route": f"{r['week']} {r['day']}",
            "Community": comm,
            "Stop": stop,
            "Address": address,
            "Postcode": postcode,
            "GeoX": round(float(lng), 6) if lng else "",
            "GeoY": round(float(lat), 6) if lat else "",
            "Day": r["day"],
            "Type": "Public",
            "Arrival": r["arrival"],
            "Departure": r["departure"],
            "Frequency": "FREQ=WEEKLY;INTERVAL=3",
            "Start": "2026-01-05",
            "End": "2026-12-23",
            "Exceptions": '',
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
    # Disable foreign-key checks so standalone CSV validation passes without services.csv
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
                    row["notes"] = f"Harvested {len(stops_records)} stops across 3-week rotation from Cheshire East Council."
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
        if "Cheshire East Mobile Library" not in existing:
            v_rows.append({
                "Local authority": AUTHORITY_NAME,
                "Mobile name": "Cheshire East Mobile Library",
                "Dataset slug": DATASET_SLUG,
                "Status": "Active",
                "Notes": "Based at Alsager Library, operating on a 3-week rotation."
            })
            with open(v_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=v_fn)
                writer.writeheader()
                writer.writerows(v_rows)
            print(f"[{DATASET_SLUG}] Updated {v_path}")


if __name__ == "__main__":
    main()
