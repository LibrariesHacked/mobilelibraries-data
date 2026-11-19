"""
Ingestion script for Warwickshire County Council Mobile Library Service.
Harvests routes, timetables, and pre-geocoded coordinates from the official
Warwickshire Mobile Libraries application (apps.warwickshire.gov.uk/MobileLibraries).
"""

from _common import clean_time, get_html, reverse_geocode_postcode
import os
import re
import csv
import json
import time
from datetime import datetime
import urllib.request
from bs4 import BeautifulSoup
from frictionless import Resource, Schema

DATASET_SLUG = "warwickshire"
AUTHORITY_NAME = "Warwickshire"
GSS_CODE = "E10000031"
BASE_URL = "https://apps.warwickshire.gov.uk"
ROUTES_URL = f"{BASE_URL}/MobileLibraries/library_routes"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}






def calculate_frequency_and_dates(dates_list):
    """Calculate frequency string, day, start_date, end_date from date list."""
    if not dates_list:
        return "", "", "", ""
    sorted_dates = sorted(dates_list)
    start_date = sorted_dates[0].strftime("%Y-%m-%d")
    end_date = sorted_dates[-1].strftime("%Y-%m-%d")
    day = sorted_dates[0].strftime("%A")

    if len(sorted_dates) > 1:
        diffs = [(sorted_dates[i+1] - sorted_dates[i]).days for i in range(len(sorted_dates)-1)]
        avg_diff = sum(diffs) / len(diffs)
        if 24 <= avg_diff <= 32:
            freq = "FREQ=WEEKLY;INTERVAL=4"
        elif 12 <= avg_diff <= 16:
            freq = "FREQ=WEEKLY;INTERVAL=2"
        elif 6 <= avg_diff <= 8:
            freq = "FREQ=WEEKLY;INTERVAL=1"
        elif 18 <= avg_diff <= 22:
            freq = "FREQ=WEEKLY;INTERVAL=3"
        elif 35 <= avg_diff <= 70:
            # Treat 5-10 week gaps (e.g. skipped holiday weeks) as 4-weekly
            freq = "FREQ=WEEKLY;INTERVAL=4"
        else:
            freq = f"FREQ=WEEKLY;INTERVAL={max(1, round(avg_diff / 7))}"
    else:
        freq = "FREQ=WEEKLY;INTERVAL=4"

    return freq, day, start_date, end_date




def main():
    """Scrape route and location pages, write data/warwickshire.csv, validate schema, and update geocache and services.csv."""
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    raw_routes_dir = os.path.join(raw_dir, "routes")
    raw_locs_dir = os.path.join(raw_dir, "locations")
    os.makedirs(raw_routes_dir, exist_ok=True)
    os.makedirs(raw_locs_dir, exist_ok=True)

    print(f"[{DATASET_SLUG}] Fetching route directory: {ROUTES_URL}")
    routes_file = os.path.join(raw_dir, "library_routes.html")
    if os.path.exists(routes_file):
        with open(routes_file, "r", encoding="utf-8") as f:
            routes_html = f.read()
    else:
        routes_html = get_html(ROUTES_URL)
        with open(routes_file, "w", encoding="utf-8") as f:
            f.write(routes_html)

    soup = BeautifulSoup(routes_html, "html.parser")
    route_links = []
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if "/MobileLibraries/library_routes/" in href:
            route_name = a.get_text(strip=True)
            full_url = BASE_URL + href if href.startswith("/") else href
            route_links.append((route_name, full_url))

    print(f"[{DATASET_SLUG}] Found {len(route_links)} routes.")

    # Location cache: loc_id -> {lat, lng, title, postcode}
    loc_cache = {}
    postcode_cache = {}

    stops_records = []

    for r_idx, (full_route_title, route_url) in enumerate(route_links, 1):
        route_id = route_url.split("/")[-1]
        route_file = os.path.join(raw_routes_dir, f"{route_id}.html")
        if os.path.exists(route_file):
            with open(route_file, "r", encoding="utf-8") as f:
                route_html = f.read()
        else:
            route_html = get_html(route_url)
            with open(route_file, "w", encoding="utf-8") as f:
                f.write(route_html)

        r_soup = BeautifulSoup(route_html, "html.parser")

        # Determine mobile vehicle and route name
        if "Hawkes Point" in full_route_title:
            mobile_lib = "Hawkes Point Mobile"
            route_name = full_route_title.replace("Hawkes Point Mobile", "").replace("-", "").strip()
        elif "Kenilworth" in full_route_title:
            mobile_lib = "Kenilworth Mobile"
            route_name = full_route_title.replace("Kenilworth Mobile", "").replace("-", "").strip()
        else:
            mobile_lib = "Warwickshire Mobile"
            route_name = full_route_title

        # Dates
        dates = []
        for li in r_soup.find_all("li"):
            text = li.get_text(strip=True)
            try:
                dt = datetime.strptime(text, "%d %B %Y")
                dates.append(dt)
            except Exception:
                pass

        freq, day_name, start_date, end_date = calculate_frequency_and_dates(dates)

        # Stops table
        table = r_soup.find("table")
        if not table:
            continue

        for tr in table.find_all("tr")[1:]:
            tds = tr.find_all("td")
            if len(tds) < 4:
                continue

            community = tds[0].get_text(strip=True)
            stop_name = tds[1].get_text(strip=True)
            arrival = clean_time(tds[2].get_text(strip=True))
            departure = clean_time(tds[3].get_text(strip=True))

            # Location link
            loc_id = ""
            a = tds[1].find("a")
            if a and "/locations/" in a.get("href", ""):
                loc_id = a.get("href").strip().split("/")[-1]

            lat, lng = "", ""
            address = f"{stop_name}, {community}"
            postcode = ""

            if loc_id:
                if loc_id in loc_cache:
                    cached = loc_cache[loc_id]
                    lat, lng, address, postcode = cached["lat"], cached["lng"], cached["address"], cached["postcode"]
                else:
                    loc_file = os.path.join(raw_locs_dir, f"{loc_id}.html")
                    try:
                        if os.path.exists(loc_file):
                            with open(loc_file, "r", encoding="utf-8") as f:
                                loc_html = f.read()
                        else:
                            loc_url = f"{BASE_URL}/MobileLibraries/locations/{loc_id}"
                            loc_html = get_html(loc_url)
                            with open(loc_file, "w", encoding="utf-8") as f:
                                f.write(loc_html)

                        l_soup = BeautifulSoup(loc_html, "html.parser")
                        h2 = l_soup.find("h2")
                        if h2:
                            address = h2.get_text(strip=True)

                        # Extract coordinates embedded as JSON in the location page HTML
                        m = re.search(r'\"lat\":\"([-0-9.]+)\",\"lng\":\"([-0-9.]+)\"', loc_html)
                        if m:
                            lat = m.group(1)
                            lng = m.group(2)
                            postcode = reverse_geocode_postcode(float(lat), float(lng), postcode_cache)

                        loc_cache[loc_id] = {
                            "lat": lat,
                            "lng": lng,
                            "address": address,
                            "postcode": postcode
                        }
                    except Exception as e:
                        print(f"    Error scraping location {loc_id}: {e}")

            stops_records.append({
                "Local authority": AUTHORITY_NAME,
                "Local authority code": GSS_CODE,
                "Mobile name": mobile_lib,
                "Route": route_name,
                "Community": community,
                "Stop": stop_name,
                "Address": address,
                "Postcode": postcode,
                "GeoX": round(float(lng), 6) if lng else "",
                "GeoY": round(float(lat), 6) if lat else "",
                "Day": day_name,
                "Type": "Public",
                "Arrival": arrival,
                "Departure": departure,
                "Frequency": (f"FREQ=WEEKLY;INTERVAL={freq}" if str(freq).isdigit() else freq),
                "Start": start_date,
                "End": end_date,
                "Exceptions": "",
                "Timetable": route_url
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
    # Skip foreign-key checks when validating the stops CSV standalone
    schema.foreign_keys = []
    resource = Resource(output_path, schema=schema)
    report = resource.validate()
    print(f"[{DATASET_SLUG}] Validation result: valid={report.valid}, errors={len(report.flatten(['rowNumber', 'fieldNumber', 'code', 'message']))}")
    if not report.valid:
        for err in report.flatten(['rowNumber', 'fieldNumber', 'code', 'message'])[:10]:
            print("  ", err)

    # Update geocache
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

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
            fieldnames = reader.fieldnames
            for row in reader:
                if row.get("dataset_slug") == DATASET_SLUG or row.get("local_authority_code") == GSS_CODE:
                    row["has_mobile_service"] = "Yes"
                    row["status"] = "Active"
                    row["source_url"] = ROUTES_URL
                    row["source_format"] = "HTML / Web App"
                    row["last_checked"] = date_stamp
                    row["last_updated"] = date_stamp
                    row["notes"] = f"Harvested {len(stops_records)} stops across 32 routes from official Web App on {date_stamp}."
                rows.append(row)
        with open(services_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[{DATASET_SLUG}] Updated {services_path}")


if __name__ == "__main__":
    main()
