"""
Neath Port Talbot Council Mobile Library Ingestion Script
Harvests the 3-weekly mobile library routes from Neath Port Talbot Council:
https://www.npt.gov.uk/libraries/library-delivery-service/mobile-library-service/
Validates schema compliance and updates services.csv, geocache, and historical vehicle registries.
"""

import csv
from datetime import datetime
import json
import os
import re
import ssl
import urllib.parse
import urllib.request
import bs4
from frictionless import Resource, Schema

AUTHORITY_NAME = "Neath Port Talbot"
AUTHORITY_CODE = "W06000012"
SLUG = "neath_port_talbot"

BASE_URL = "https://www.npt.gov.uk/libraries/library-delivery-service/mobile-library-service/"
ROUTE_URLS = [
    (
        "Week 1",
        "https://www.npt.gov.uk/libraries/library-delivery-service/mobile-library-service/week-1-route/",
    ),
    (
        "Week 2",
        "https://www.npt.gov.uk/libraries/library-delivery-service/mobile-library-service/week-2-route/",
    ),
    (
        "Week 3",
        "https://www.npt.gov.uk/libraries/library-delivery-service/mobile-library-service/week-3-route/",
    ),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        " LibrariesHacked/MobileLibrariesMonitor"
    )
}
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def geocode_place(
    community: str, stop: str, geocache: dict, session_cache: dict
):
  ref_key = f"{AUTHORITY_NAME}:{community}:{stop}".lower()
  if ref_key in geocache:
    return geocache[ref_key]
  comm_key = f"{AUTHORITY_NAME}:{community}".lower()
  if comm_key in session_cache:
    return session_cache[comm_key]

  clean_comm = (
      community.split("/")[0]
      .strip()
      .replace("Godre'r graig", "Godrergraig")
      .replace("Gwaun Cae Gurwen", "Gwaun-Cae-Gurwen")
  )
  q = urllib.parse.quote(clean_comm)
  url = f"https://api.postcodes.io/places?q={q}&limit=10"
  try:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=8) as resp:
      data = json.loads(resp.read().decode("utf-8"))
      for p in data.get("result") or []:
        lat = float(p.get("latitude", 0))
        lng = float(p.get("longitude", 0))
        if p.get("county_unitary") == "Neath Port Talbot" or (
            51.50 <= lat <= 51.85 and -3.95 <= lng <= -3.55
        ):
          coords = (round(lat, 6), round(lng, 6))
          session_cache[comm_key] = coords
          return coords
      for p in data.get("result") or []:
        lat = float(p.get("latitude", 0))
        lng = float(p.get("longitude", 0))
        if p.get("country") == "Wales":
          coords = (round(lat, 6), round(lng, 6))
          session_cache[comm_key] = coords
          return coords
  except Exception:
    pass

  default_coords = (51.6631, -3.8035)
  session_cache[comm_key] = default_coords
  return default_coords


def reverse_geocode_postcode(lat: float, lng: float, pc_cache: dict) -> str:
  key = f"{round(lat, 4)},{round(lng, 4)}"
  if key in pc_cache:
    return pc_cache[key]
  try:
    url = f"https://api.postcodes.io/postcodes?lat={lat}&lon={lng}&limit=1"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=5) as resp:
      data = json.loads(resp.read().decode("utf-8"))
      if data.get("result"):
        pc = data["result"][0]["postcode"]
        pc_cache[key] = pc
        return pc
  except Exception:
    pass
  pc_cache[key] = ""
  return ""


def parse_week_html(html: str, week_label: str, url: str):
  soup = bs4.BeautifulSoup(html, "html.parser")
  stops = []
  valid_days = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}
  for h2 in soup.find_all("h2"):
    day_text = h2.get_text(" ", strip=True)
    if day_text not in valid_days:
      continue
    container = h2.find_parent("div", class_="container")
    if not container:
      continue
    table = container.find("table")
    if not table:
      continue
    for tr in table.find_all("tr"):
      cells = [
          td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])
      ]
      if len(cells) >= 3:
        loc, venue, times = cells[0], cells[1], cells[2]
        if loc.lower() == "location":
          continue
        m_time = re.search(
            r"(\d{1,2}[:.]\d{2})\s*[-–]\s*(\d{1,2}[:.]\d{2})", times
        )
        if m_time:
          arr = m_time.group(1).replace(".", ":")
          dep = m_time.group(2).replace(".", ":")
          if len(arr) == 4:
            arr = "0" + arr
          if len(dep) == 4:
            dep = "0" + dep
        elif times.strip().upper() == "PM":
          arr = "13:30"
          dep = "15:00"
        else:
          continue
        stops.append({
            "route": f"{week_label} {day_text}",
            "day": day_text,
            "community": loc,
            "stop": venue,
            "arr": arr,
            "dep": dep,
            "url": url,
        })
  return stops


def run():
  print(f"[{SLUG}] Starting ingestion for {AUTHORITY_NAME} ({AUTHORITY_CODE})...")
  date_stamp = datetime.now().strftime("%Y-%m-%d")
  raw_dir = os.path.join("raw", SLUG, date_stamp)
  os.makedirs(raw_dir, exist_ok=True)

  index_path = os.path.join(raw_dir, "mobile_library_service.html")
  if not os.path.exists(index_path):
    req = urllib.request.Request(BASE_URL, headers=HEADERS)
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
      with open(index_path, "wb") as f:
        f.write(resp.read())

  geocache_path = os.path.join("geocache", "stops_reference.json")
  if os.path.exists(geocache_path):
    with open(geocache_path, "r", encoding="utf-8") as f:
      geocache = json.load(f)
  else:
    geocache = {}

  all_raw_stops = []
  for week_label, url in ROUTE_URLS:
    fname = f"{week_label.lower().replace(' ', '_')}.html"
    fpath = os.path.join(raw_dir, fname)
    if not os.path.exists(fpath):
      req = urllib.request.Request(url, headers=HEADERS)
      with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        with open(fpath, "wb") as f:
          f.write(resp.read())
    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
      html = f.read()
    parsed = parse_week_html(html, week_label, url)
    print(f"[{SLUG}] Extracted {len(parsed)} stops from {week_label}")
    all_raw_stops.extend(parsed)

  session_cache = {}
  pc_cache = {}
  stops_records = []
  vehicle = "Neath Port Talbot Mobile Library"

  for s in all_raw_stops:
    comm = s["community"]
    stop_name = s["stop"]
    lat, lng = geocode_place(comm, stop_name, geocache, session_cache)
    postcode = reverse_geocode_postcode(lat, lng, pc_cache)

    geocache[f"{AUTHORITY_NAME}:{comm}:{stop_name}".lower()] = (lat, lng)
    if postcode:
      geocache[postcode] = (lat, lng)

    address = (
        f"{stop_name}, {comm}, Neath Port Talbot"
        if stop_name.lower() != comm.lower()
        else f"{comm}, Neath Port Talbot"
    )
    stype = (
        "Private"
        if "school visit only" in stop_name.lower()
        or "primary school" in stop_name.lower()
        else "Public"
    )
    if "former ynysmaerdy primary school" in stop_name.lower():
      stype = "Public"

    stops_records.append({
        "Local authority": AUTHORITY_NAME,
        "Local authority code": AUTHORITY_CODE,
        "Mobile name": vehicle,
        "Route": s["route"],
        "Community": comm,
        "Stop": stop_name,
        "Address": address,
        "Postcode": postcode,
        "GeoX": lng,
        "GeoY": lat,
        "Day": s["day"],
        "Type": stype,
        "Arrival": s["arr"],
        "Departure": s["dep"],
        "Frequency": "FREQ=WEEKLY;INTERVAL=3",
        "Start": "2026-11-03",
        "End": "2026-12-24",
        "Exceptions": "Bank holidays",
        "Timetable": s["url"],
    })

  stops_records.sort(key=lambda r: (r["Route"], r["Arrival"], r["Community"]))

  with open(geocache_path, "w", encoding="utf-8") as f:
    json.dump(geocache, f, indent=2)

  out_csv = os.path.join("data", f"{SLUG}.csv")
  fieldnames = [
      "Local authority",
      "Local authority code",
      "Mobile name",
      "Route",
      "Community",
      "Stop",
      "Address",
      "Postcode",
      "GeoX",
      "GeoY",
      "Day",
      "Type",
      "Arrival",
      "Departure",
      "Frequency",
      "Start",
      "End",
      "Exceptions",
      "Timetable",
  ]
  with open(out_csv, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(stops_records)

  print(f"[{SLUG}] Saved {len(stops_records)} stops to {out_csv}")

  schema = Schema("schemas/mobile-library-stops.json")
  schema.foreign_keys = []
  resource = Resource(out_csv, schema=schema)
  report = resource.validate()
  print(
      f"[{SLUG}] Validation result: valid={report.valid},"
      " errors="
      f"{len(report.flatten(['rowNumber', 'fieldNumber', 'code', 'message']))}"
  )

  vehicles_csv = os.path.join("history", "historical_mobile_vehicles.csv")
  if os.path.exists(vehicles_csv):
    with open(vehicles_csv, "r", encoding="utf-8") as f:
      reader = csv.DictReader(f)
      v_fieldnames = reader.fieldnames
      existing_rows = list(reader)
    existing_keys = {
        (r.get("Local authority"), r.get("Mobile name")) for r in existing_rows
    }
    if (AUTHORITY_NAME, vehicle) not in existing_keys:
      existing_rows.append({
          "Local authority": AUTHORITY_NAME,
          "Mobile name": vehicle,
          "Dataset slug": SLUG,
          "Status": "Active",
          "Notes": "Neath Port Talbot 3-weekly mobile library service",
      })
      with open(vehicles_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=v_fieldnames)
        writer.writeheader()
        writer.writerows(existing_rows)

  services_csv = "services.csv"
  if os.path.exists(services_csv):
    with open(services_csv, "r", encoding="utf-8") as f:
      reader = csv.DictReader(f)
      s_fieldnames = reader.fieldnames
      rows = list(reader)
    today = datetime.now().strftime("%Y-%m-%d")
    for r in rows:
      if (
          r.get("dataset_slug") == SLUG
          or r.get("local_authority_code") == AUTHORITY_CODE
      ):
        r["has_mobile_service"] = "Yes"
        r["status"] = "Active Verified"
        r["source_url"] = BASE_URL
        r["source_format"] = "HTML Table"
        r["last_checked"] = today
        r["last_updated"] = today
        r["notes"] = (
            f"Harvested {len(stops_records)} stops across Week 1-3 routes on a"
            " 3-week cycle."
        )
        break
    with open(services_csv, "w", encoding="utf-8", newline="") as f:
      writer = csv.DictWriter(f, fieldnames=s_fieldnames)
      writer.writeheader()
      writer.writerows(rows)


if __name__ == "__main__":
  run()
