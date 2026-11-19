"""
Conwy County Borough Council Mobile Library Ingestion Script
Harvests the 4-weekly routes from Conwy's official mobile library pages:
https://www.conwy.gov.uk/en/Resident/Libraries-Museums-and-Archives/Libraries/Mobile-library-routes/Mobile-library-route-schedules.aspx
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

AUTHORITY_NAME = "Conwy"
AUTHORITY_CODE = "W06000003"
SLUG = "conwy"

BASE_URL = "https://www.conwy.gov.uk/en/Resident/Libraries-Museums-and-Archives/Libraries/Mobile-library-routes/All-mobile-library-stops.aspx"
ROUTE_URLS = [
    (
        "Route 1",
        "Tuesday",
        "https://www.conwy.gov.uk/en/Resident/Libraries-Museums-and-Archives/Libraries/Mobile-library-routes/Conwy-Mobile-Library-Route-1.aspx",
    ),
    (
        "Route 2",
        "Thursday",
        "https://www.conwy.gov.uk/en/Resident/Libraries-Museums-and-Archives/Libraries/Mobile-library-routes/Conwy-Mobile-Library-Route-2.aspx",
    ),
    (
        "Route 3",
        "Tuesday",
        "https://www.conwy.gov.uk/en/Resident/Libraries-Museums-and-Archives/Libraries/Mobile-library-routes/Conwy-Mobile-Library-Route-3.aspx",
    ),
    (
        "Route 4",
        "Thursday",
        "https://www.conwy.gov.uk/en/Resident/Libraries-Museums-and-Archives/Libraries/Mobile-library-routes/Conwy-Mobile-Library-Route-4.aspx",
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
      community.replace("Llanfair TH", "Llanfair Talhaiarn")
      .replace("Llanfihangel GM", "Llanfihangel Glyn Myfyr")
      .replace("Ty’n y Groes", "Tyn-y-groes")
      .replace("Tal y Bont", "Tal-y-bont")
      .replace("Betws y Coed", "Betws-y-Coed")
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
        if p.get("county_unitary") == "Conwy" or (
            52.95 <= lat <= 53.35 and -4.05 <= lng <= -3.45
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

  default_coords = (53.2825, -3.8295)
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


def parse_route_html(html: str, route_name: str, day_name: str, url: str):
  soup = bs4.BeautifulSoup(html, "html.parser")
  stops = []
  for table in soup.find_all("table"):
    for tr in table.find_all("tr"):
      cells = [
          td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])
      ]
      if len(cells) >= 3:
        village, loc, times = cells[0], cells[1], cells[2]
        if village.lower() in ["village", "town or village"]:
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
          stops.append({
              "route": route_name,
              "day": day_name,
              "community": village,
              "stop": loc,
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

  # Save all stops index page
  index_path = os.path.join(raw_dir, "all_stops.html")
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
  for route_name, day_name, url in ROUTE_URLS:
    fname = f"{route_name.lower().replace(' ', '_')}.html"
    fpath = os.path.join(raw_dir, fname)
    if not os.path.exists(fpath):
      req = urllib.request.Request(url, headers=HEADERS)
      with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        with open(fpath, "wb") as f:
          f.write(resp.read())
    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
      html = f.read()
    parsed = parse_route_html(html, route_name, day_name, url)
    print(f"[{SLUG}] Extracted {len(parsed)} stops from {route_name}")
    all_raw_stops.extend(parsed)

  session_cache = {}
  pc_cache = {}
  stops_records = []
  vehicle = "Conwy Mobile Library"

  for s in all_raw_stops:
    comm = s["community"]
    stop_name = s["stop"]
    lat, lng = geocode_place(comm, stop_name, geocache, session_cache)
    postcode = reverse_geocode_postcode(lat, lng, pc_cache)

    geocache[f"{AUTHORITY_NAME}:{comm}:{stop_name}".lower()] = (lat, lng)
    if postcode:
      geocache[postcode] = (lat, lng)

    address = (
        f"{stop_name}, {comm}, Conwy"
        if stop_name.lower() != comm.lower()
        else f"{comm}, Conwy"
    )
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
        "Type": "Public",
        "Arrival": s["arr"],
        "Departure": s["dep"],
        "Frequency": "FREQ=WEEKLY;INTERVAL=4",
        "Start": "2026-04-09",
        "End": "2027-03-30",
        "Exceptions": "Public holidays and Christmas",
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

  # Update historical vehicles
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
          "Notes": "Conwy 4-weekly rural mobile library service",
      })
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
            f"Harvested {len(stops_records)} stops across 4 routes on a 4-week"
            " cycle."
        )
        break
    with open(services_csv, "w", encoding="utf-8", newline="") as f:
      writer = csv.DictWriter(f, fieldnames=s_fieldnames)
      writer.writeheader()
      writer.writerows(rows)


if __name__ == "__main__":
  run()
