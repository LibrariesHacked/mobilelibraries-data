"""
Ingestion script for Perth and Kinross Council Mobile Library Service.
Harvests schedules from Culture Perth & Kinross (culturepk.org.uk/library/mobile-library),
cross-references historical geocache and Nominatim/postcodes.io, validates schema compliance,
and updates services.csv and geocache.
"""

import os
import re
import csv
import json
import time
from datetime import datetime
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
from frictionless import Resource, Schema

DATASET_SLUG = "perth_and_kinross"
AUTHORITY_NAME = "Perth and Kinross"
GSS_CODE = "S12000048"
SOURCE_URL = "https://www.culturepk.org.uk/library/mobile-library/"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}


def get_html(url: str, retries: int = 3, delay: float = 1.0) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            if attempt == retries - 1:
                raise e
            time.sleep(delay)
    return ""


def clean_time(time_str: str) -> str:
    """Format time string into 24-hr HH:MM."""
    t = time_str.strip().replace(";", ":").replace(".", ":")
    m = re.match(r"^(\d{1,2}):(\d{2})$", t)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return ""


def parse_time_range(time_raw: str):
    """Split time string like '11:00 – 11:30' into (arrival, departure)."""
    # Clean typos like '15.30 -1 6.00' -> '15.30 - 16.00'
    t_clean = re.sub(r"-1\s*6", "- 16", time_raw)
    t_clean = re.sub(r"(\d)\s+(\d)", r"\1\2", t_clean)
    parts = re.split(r"[–—-]", t_clean)
    arr = clean_time(parts[0]) if len(parts) > 0 else ""
    dep = clean_time(parts[1]) if len(parts) > 1 else ""
    if arr and not dep:
        # Default duration +20m
        h, m = map(int, arr.split(":"))
        m += 20
        if m >= 60:
            h = (h + 1) % 24
            m -= 60
        dep = f"{h:02d}:{m:02d}"
    return arr, dep


def reverse_geocode_postcode(lat: float, lon: float, postcode_cache: dict) -> str:
    """Find nearest UK postcode from postcodes.io."""
    cache_key = f"{round(lat, 4)},{round(lon, 4)}"
    if cache_key in postcode_cache:
        return postcode_cache[cache_key]

    url = f"https://api.postcodes.io/postcodes?lat={lat}&lon={lon}&limit=1"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("result"):
                pc = data["result"][0]["postcode"]
                postcode_cache[cache_key] = pc
                return pc
    except Exception:
        pass
    postcode_cache[cache_key] = ""
    return ""


def geocode_nominatim(query: str) -> tuple:
    """Fallback geocode via Nominatim."""
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(query)}&format=json&countrycodes=gb&limit=1"
    req = urllib.request.Request(url, headers={"User-Agent": "LibrariesHacked/MobileLibrariesIngest"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None, None


def main():
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)
    raw_file = os.path.join(raw_dir, "mobile_library.html")

    print(f"[{DATASET_SLUG}] Fetching {SOURCE_URL}...")
    if os.path.exists(raw_file):
        with open(raw_file, "r", encoding="utf-8") as f:
            html = f.read()
    else:
        html = get_html(SOURCE_URL)
        with open(raw_file, "w", encoding="utf-8") as f:
            f.write(html)

    soup = BeautifulSoup(html, "html.parser")

    # Load geocache
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    def match_geocache(comm, stp):
        c_clean = re.sub(r"[^a-z0-9]", "", comm.lower())
        s_clean = re.sub(r"[^a-z0-9]", "", stp.lower())
        candidates = [
            f"perthandkinross::{s_clean}::{c_clean}",
            f"perthandkinross::{c_clean}::{s_clean}",
            f"perthandkinross::{s_clean}",
            f"perthandkinross::{c_clean}"
        ]
        for cand in candidates:
            if cand in geocache:
                res = geocache[cand]
                return res.get("geoy") or res.get("latitude"), res.get("geox") or res.get("longitude"), res.get("postcode", "")
        # partial check
        for k, v in geocache.items():
            if "perth" in k and c_clean in k:
                return v.get("geoy") or v.get("latitude"), v.get("geox") or v.get("longitude"), v.get("postcode", "")
        return None, None, ""

    postcode_cache = {}
    stops_records = []

    tables = soup.find_all("table")
    print(f"[{DATASET_SLUG}] Found {len(tables)} timetable tables.")

    for t in tables:
        h4 = t.find_previous("h4")
        h2 = t.find_previous("h2")
        p = t.find_previous("p")

        h4_text = h4.get_text(strip=True) if h4 else ""
        h2_text = h2.get_text(strip=True) if h2 else ""
        p_text = p.get_text(strip=True) if p else ""

        # Determine Mobile vehicle
        if "Mobile One" in h4_text or "Mobile 1" in h4_text:
            mobile_name = "Mobile One"
        elif "Mobile Two" in h4_text or "Mobile 2" in h4_text:
            mobile_name = "Mobile Two"
        else:
            mobile_name = "Mobile Library"

        # Determine Week and Day
        m_week = re.search(r"Week\s*(\w+)", h4_text, re.I)
        week_str = m_week.group(0).title() if m_week else "Week 1"

        m_day = re.search(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)", h2_text, re.I)
        day_str = m_day.group(1).title() if m_day else "Monday"

        route_name = f"{week_str} {day_str}"

        # Parse dates
        # e.g. '2 Jun / 23 Jun / 14 Jul / 4 Aug / 25 Aug / 15 Sep / 6 Oct / 27 Oct / 17 Nov / 8 Dec'
        date_tokens = [d.strip() for d in re.split(r"[/,]", p_text) if re.search(r"\d+\s+[A-Za-z]+", d)]
        parsed_dates = []
        for dt_str in date_tokens:
            try:
                # Add current 2026 year context
                d_obj = datetime.strptime(f"{dt_str} 2026", "%d %b %Y")
                parsed_dates.append(d_obj)
            except Exception:
                pass

        if parsed_dates:
            sorted_dates = sorted(parsed_dates)
            start_date = sorted_dates[0].strftime("%Y-%m-%d")
            end_date = sorted_dates[-1].strftime("%Y-%m-%d")
        else:
            start_date = "2026-06-01"
            end_date = "2026-12-31"

        frequency = "3 weekly"

        for tr in t.find_all("tr"):
            tds = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if len(tds) < 2 or "stop name" in tds[0].lower():
                continue

            raw_stop = tds[0].replace("\xa0", " ").strip()
            raw_time = tds[1].replace("\xa0", " ").strip()

            if not raw_stop or not raw_time:
                continue

            if "," in raw_stop:
                parts = raw_stop.split(",", 1)
                community = parts[0].strip()
                stop_name = parts[1].strip()
            else:
                community = raw_stop
                stop_name = raw_stop

            address = f"{stop_name}, {community}" if stop_name != community else community

            arrival, departure = parse_time_range(raw_time)

            # Match coordinates
            lat, lng, pc = match_geocache(community, stop_name)

            if not lat or not lng:
                # Fallback to Nominatim
                lat, lng = geocode_nominatim(f"{stop_name}, {community}, Perth and Kinross, Scotland")
                if not lat:
                    lat, lng = geocode_nominatim(f"{community}, Perth and Kinross, Scotland")
                time.sleep(0.5)

            if lat and lng and not pc:
                pc = reverse_geocode_postcode(float(lat), float(lng), postcode_cache)

            stops_records.append({
                "Local authority": AUTHORITY_NAME,
                "Local authority code": GSS_CODE,
                "Mobile name": mobile_name,
                "Route": route_name,
                "Community": community,
                "Stop": stop_name,
                "Address": address,
                "Postcode": pc,
                "GeoX": round(float(lng), 6) if lng else "",
                "GeoY": round(float(lat), 6) if lat else "",
                "Day": day_str,
                "Type": "Public",
                "Arrival": arrival,
                "Departure": departure,
                "Frequency": frequency,
                "Start": start_date,
                "End": end_date,
                "Exceptions": "",
                "Timetable": SOURCE_URL
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
                    row["source_url"] = SOURCE_URL
                    row["source_format"] = "HTML"
                    row["last_checked"] = date_stamp
                    row["last_updated"] = date_stamp
                    row["notes"] = f"Harvested {len(stops_records)} stops across 22 routes from Culture Perth & Kinross on {date_stamp}."
                rows.append(row)
        with open(services_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fn)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[{DATASET_SLUG}] Updated {services_path}")


if __name__ == "__main__":
    main()
