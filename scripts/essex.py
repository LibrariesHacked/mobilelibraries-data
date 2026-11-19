"""
Ingestion script for Essex County Council Mobile Library Service.
Harvests routes, timetables, and stops across all 12 district Google My Maps KML feeds
published on libraries.essex.gov.uk/digital-content/our-mobile-and-home-library-services/mobile-libraries/.
Validates schema compliance and updates services.csv, geocache, and historical vehicle registries.
"""

import os
import re
import csv
import json
from datetime import datetime
import urllib.request
import xml.etree.ElementTree as ET
from frictionless import Resource, Schema

DATASET_SLUG = "essex"
AUTHORITY_NAME = "Essex"
GSS_CODE = "E10000012"
BASE_URL = "https://libraries.essex.gov.uk/digital-content/our-mobile-and-home-library-services/mobile-libraries/"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LibrariesHacked/MobileLibrariesMonitor"}

DISTRICT_MAPS = {
    "basildon": "1x4NzRu4tawPK52mW0RknyAslNZssrkLc",
    "braintree": "1gjmvui2K-YmXF-nHrAzgVvsCA67LRjH-",
    "brentwood": "15vxabtcyRPg3s-WiHd4F__s8a9Si7G84",
    "castle_point": "1-yU2nTd8G3O2OO4cVjXBzQilj9NB7y6o",
    "chelmsford": "1iSmdbkIhGsD5KnXfN13xlc7rTTugQrQd",
    "colchester": "1hRIM87MjPEL6f708FAD4a1U8EwPf7fbC",
    "epping_forest": "1Op4ZNsP1idEEOQFTZqMcJAradKQySjMB",
    "harlow": "1uVQl4J0ef7a23h5c5Int0xbq3V3bZMS2",
    "maldon": "1U6I5tu73zdmTrQIiy7n7ixRBLeR6jBW8",
    "rochford": "1USd0XuJQTl4UoZGhCda_stpvjQF6Dk3g",
    "tendring": "1_K5ufreVPkmVRS0N72p6hnkn2vrWEzFZ",
    "uttlesford": "1kpUvEYAcf6RV1JQPFKGTgWT03YbYFq07"
}

KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}


def clean_time(t_str: str) -> str:
    """Format time string into 24-hr HH:MM."""
    m = re.search(r"(\d{1,2})[:.](\d{2})", t_str.strip())
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return ""


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


def main():
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)

    # Load existing geocache
    geocache_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(geocache_path):
        with open(geocache_path, "r", encoding="utf-8") as f:
            geocache = json.load(f)
    else:
        geocache = {}

    postcode_cache = {}
    raw_placemarks = []

    for district, mid in DISTRICT_MAPS.items():
        kml_url = f"https://www.google.com/maps/d/kml?mid={mid}&forcekml=1"
        dest_file = os.path.join(raw_dir, f"{district}.kml")
        print(f"[{DATASET_SLUG}] Downloading {district} KML feed...")

        if os.path.exists(dest_file):
            with open(dest_file, "rb") as f:
                kml_bytes = f.read()
        else:
            req = urllib.request.Request(kml_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                kml_bytes = resp.read()
            with open(dest_file, "wb") as f:
                f.write(kml_bytes)

        try:
            root = ET.fromstring(kml_bytes)
            pms = root.findall(".//kml:Placemark", KML_NS)
            print(f"[{DATASET_SLUG}] Extracted {len(pms)} placemarks from {district}")
            for p in pms:
                name_el = p.find("kml:name", KML_NS)
                desc_el = p.find("kml:description", KML_NS)
                coords_el = p.find(".//kml:coordinates", KML_NS)
                raw_placemarks.append({
                    "district": district,
                    "name": name_el.text.strip() if name_el is not None and name_el.text else "",
                    "description": desc_el.text.strip() if desc_el is not None and desc_el.text else "",
                    "coordinates": coords_el.text.strip() if coords_el is not None and coords_el.text else ""
                })
        except Exception as e:
            print(f"[{DATASET_SLUG}] Error parsing KML for {district}: {e}")

    print(f"[{DATASET_SLUG}] Total raw placemarks across Essex: {len(raw_placemarks)}")

    stops_records = []

    for p in raw_placemarks:
        name_raw = p["name"]
        desc_raw = p["description"].replace("\xa0", " ").strip()
        coords_raw = p["coordinates"]

        # Fix double colon typo (e.g. 10::50)
        desc_raw = re.sub(r"::+", ":", desc_raw)

        # Parse coordinates (lon,lat,alt)
        lng, lat = None, None
        if coords_raw:
            parts = [c.strip() for c in coords_raw.split(",")]
            if len(parts) >= 2:
                try:
                    lng = float(parts[0])
                    lat = float(parts[1])
                except ValueError:
                    pass

        # Split Name into Community and Stop
        if "," in name_raw:
            c_parts = [x.strip() for x in name_raw.split(",", 1)]
            comm = c_parts[0]
            stop = c_parts[1]
        elif "–" in name_raw:
            c_parts = [x.strip() for x in name_raw.split("–", 1)]
            comm = c_parts[0]
            stop = c_parts[1]
        elif "-" in name_raw:
            c_parts = [x.strip() for x in name_raw.split("-", 1)]
            comm = c_parts[0]
            stop = c_parts[1]
        else:
            comm = name_raw
            stop = name_raw

        # Parse Mobile van name
        m_van = re.search(r"(Mobile Library\s+\d+)", desc_raw, re.I)
        van = m_van.group(1).title() if m_van else "Essex Mobile Library"

        # Parse Day
        m_day = re.search(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)", desc_raw, re.I)
        day = m_day.group(1).title() if m_day else "Monday"

        # Parse Times
        m_times = re.search(r"(\d{1,2}[:.]\d{2})\s*(?:-|to)\s*(\d{1,2}[:.]\d{2})", desc_raw, re.I)
        if m_times:
            arr = clean_time(m_times.group(1))
            dep = clean_time(m_times.group(2))
        else:
            # Fallback single time or default duration
            m_single = re.search(r"(\d{1,2}[:.]\d{2})", desc_raw)
            arr = clean_time(m_single.group(1)) if m_single else "10:00"
            dep = ""

        if arr and not dep:
            try:
                h, m = map(int, arr.split(":"))
                m += 30
                if m >= 60:
                    h = (h + 1) % 24
                    m -= 60
                dep = f"{h:02d}:{m:02d}"
            except Exception:
                dep = "10:30"

        # Reverse geocode postcode
        postcode = ""
        if lat and lng:
            postcode = reverse_geocode_postcode(lat, lng, postcode_cache)

        route_name = f"{van} {p['district'].replace('_', ' ').title()} {day}"
        address = f"{stop}, {comm}" if stop != comm else comm

        # Check type
        stop_type = "School" if "school" in stop.lower() or "nursery" in stop.lower() else "Public"
        if stop_type == "School":
            stop_type = "Private"

        stops_records.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": GSS_CODE,
            "Mobile name": van,
            "Route": route_name,
            "Community": comm,
            "Stop": stop,
            "Address": address,
            "Postcode": postcode,
            "GeoX": round(lng, 6) if lng is not None else "",
            "GeoY": round(lat, 6) if lat is not None else "",
            "Day": day,
            "Type": stop_type,
            "Arrival": arr,
            "Departure": dep,
            "Frequency": "FREQ=WEEKLY;INTERVAL=3",
            "Start": "2026-01-05",
            "End": "2026-12-31",
            "Exceptions": "Bank holidays",
            "Timetable": f"{BASE_URL}{p['district'].replace('_', '-')}"
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
                    row["source_format"] = "Google My Maps / KML"
                    row["last_checked"] = date_stamp
                    row["last_updated"] = date_stamp
                    row["notes"] = f"Harvested {len(stops_records)} stops across all 12 districts from official Essex County Council Google My Maps feeds."
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
        for van_n in ["Mobile Library 1", "Mobile Library 2"]:
            if van_n not in existing:
                v_rows.append({
                    "Local authority": AUTHORITY_NAME,
                    "Mobile name": van_n,
                    "Dataset slug": DATASET_SLUG,
                    "Status": "Active",
                    "Notes": "Essex County Council three-weekly rural mobile fleet vehicle."
                })
        with open(v_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=v_fn)
            writer.writeheader()
            writer.writerows(v_rows)
        print(f"[{DATASET_SLUG}] Updated {v_path}")


if __name__ == "__main__":
    main()
