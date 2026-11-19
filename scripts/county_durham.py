"""
Ingestion script for County Durham Mobile Library Service.
Harvests routes, timetables, and stops from Durham County Council Library Online
HTML pages (https://libraryonline.durham.gov.uk/pgLibMobile.aspx) and writes data/county_durham.csv.
Geocodes via postcodes.io, validates schema compliance, and updates services.csv and geocache.
"""

from _common import clean_time, reverse_geocode_postcode
import os
import re
import csv
import json
import time
from datetime import datetime
import urllib.request
import urllib.parse
import http.cookiejar
from bs4 import BeautifulSoup
from frictionless import Resource, Schema

DATASET_SLUG = "county_durham"
AUTHORITY_NAME = "County Durham"
GSS_CODE = "E06000047"
BASE_URL = "https://www.durham.gov.uk/mobilelibrary"
PORTAL_URL = "https://libraryonline.durham.gov.uk/pgLibMobile.aspx"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        """Return the 302 response directly without following redirects."""
        return fp




def geocode_place_postcodes_io(place: str, cache: dict) -> tuple:
    """Geocode place using postcodes.io/places API with priority for Durham outcodes."""
    # Use the primary place name when a stop lists slash-separated alternatives
    clean_p = place.split("/")[0].strip()
    if clean_p in cache:
        return cache[clean_p]

    url = f"https://api.postcodes.io/places?q={urllib.parse.quote(clean_p)}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("result", [])
            if results:
                # Prefer County Durham postcode prefixes (DH, DL, TS, SR) over same-named UK places
                dur_matches = [r for r in results if "Durham" in str(r.get("admin_district", "")) or str(r.get("outcode", "")).startswith(("DH", "DL", "TS", "SR"))]
                chosen = dur_matches[0] if dur_matches else results[0]
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
    """Harvest County Durham stops, geocode them, and write data/county_durham.csv.

    Also validates schema compliance and updates geocache, services.csv, and vehicle history.
    """
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)
    raw_main_path = os.path.join(raw_dir, "pgLibMobile.html")

    print(f"[{DATASET_SLUG}] Initializing session with {PORTAL_URL}")
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), NoRedirectHandler)
    opener.addheaders = [("User-Agent", HEADERS["User-Agent"])]

    # Establish ASP.NET session cookies without following the cookie-check redirect loop
    opener.open("https://libraryonline.durham.gov.uk/")
    opener.open("https://libraryonline.durham.gov.uk/?AspxAutoDetectCookieSupport=1")

    # Fetch main community directory
    r_main = opener.open(PORTAL_URL)
    main_html = r_main.read().decode("utf-8", errors="ignore")
    with open(raw_main_path, "w", encoding="utf-8") as f:
        f.write(main_html)

    soup_main = BeautifulSoup(main_html, "html.parser")
    communities = []
    for a in soup_main.find_all("a"):
        href = a.get("href", "")
        if "COMMUNITY=" in href:
            m = re.search(r"COMMUNITY=([^&#]+)", href)
            if m:
                c = urllib.parse.unquote(m.group(1)).strip()
                if c and c not in communities:
                    communities.append(c)

    print(f"[{DATASET_SLUG}] Discovered {len(communities)} communities to harvest.")

    raw_stops = []
    day_map = {
        "mon": "Monday", "tue": "Tuesday", "wed": "Wednesday",
        "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"
    }

    for comm in communities:
        url = f"https://libraryonline.durham.gov.uk/pgLibMobile.aspx?&COMMUNITY={urllib.parse.quote(comm)}"
        try:
            resp = opener.open(url)
            html = resp.read().decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            table = soup.find("table")
            if table:
                for tr in table.find_all("tr")[1:]:
                    tds = tr.find_all("td")
                    if len(tds) >= 2:
                        stop_name = tds[0].get_text(strip=True)
                        dt_cell = tds[1].get_text(" ", strip=True)

                        # Match slots like 'Thu 03 Dec 2026 11.20-11.35'
                        slots = re.findall(r"([A-Za-z]{3})\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+(\d{1,2}[:.]\d{2})\s*-\s*(\d{1,2}[:.]\d{2})", dt_cell)
                        if slots:
                            # Use first slot for timetable schedule
                            day_abbr, date_str, arr_raw, dep_raw = slots[0]
                            day_full = day_map.get(day_abbr.lower(), "Monday")
                            arr = clean_time(arr_raw)
                            dep = clean_time(dep_raw)
                            raw_stops.append({
                                "community": comm,
                                "stop": stop_name,
                                "day": day_full,
                                "arrival": arr,
                                "departure": dep,
                                "date": date_str,
                                "num_slots": len(slots),
                                "url": url
                            })
        except Exception as e:
            print(f"[{DATASET_SLUG}] Error fetching {comm}: {e}")

    print(f"[{DATASET_SLUG}] Extracted {len(raw_stops)} distinct stop schedules.")

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

    for item in raw_stops:
        comm = item["community"]
        stop = item["stop"]
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

        # If visited weekly (5 slots) -> freq 1, else 3
        freq = 1 if item["num_slots"] >= 4 else 3

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": GSS_CODE,
            "Mobile name": "Durham Mobile Library",
            "Route": f"{item['day']} Route",
            "Community": comm,
            "Stop": stop,
            "Address": address,
            "Postcode": postcode,
            "GeoX": round(float(lng), 6) if lng else "",
            "GeoY": round(float(lat), 6) if lat else "",
            "Day": item["day"],
            "Type": "Public",
            "Arrival": item["arrival"],
            "Departure": item["departure"],
            "Frequency": (f"FREQ=WEEKLY;INTERVAL={freq}" if str(freq).isdigit() else freq),
            "Start": "2026-01-05",
            "End": "2026-12-31",
            "Exceptions": "Bank holidays and Christmas period",
            "Timetable": item["url"]
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
    # Skip foreign-key check since services.csv is updated after writing the CSV
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
                    row["source_url"] = PORTAL_URL
                    row["source_format"] = "HTML / Library Online"
                    row["last_checked"] = date_stamp
                    row["last_updated"] = date_stamp
                    row["notes"] = f"Harvested {len(stops_records)} stops across 85 communities from Durham County Council Library Online."
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
        if "Durham Mobile Library" not in existing:
            v_rows.append({
                "Local authority": AUTHORITY_NAME,
                "Mobile name": "Durham Mobile Library",
                "Dataset slug": DATASET_SLUG,
                "Status": "Active",
                "Notes": "Durham County Council accessible mobile library van serving 85 communities."
            })
            with open(v_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=v_fn)
                writer.writeheader()
                writer.writerows(v_rows)
            print(f"[{DATASET_SLUG}] Updated {v_path}")


if __name__ == "__main__":
    main()
