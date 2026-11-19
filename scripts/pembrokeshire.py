"""
Pembrokeshire County Council Mobile Library Ingestion Script
Harvests the 4-weekly routes A to H from Pembrokeshire's official mobile library page:
https://www.pembrokeshire.gov.uk/pembrokeshire-libraries/mobile-library-service-and-library-at-home
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

AUTHORITY_NAME = "Pembrokeshire"
AUTHORITY_CODE = "W06000009"
SLUG = "pembrokeshire"

BASE_URL = "https://www.pembrokeshire.gov.uk/pembrokeshire-libraries/mobile-library-service-and-library-at-home"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        " LibrariesHacked/MobileLibrariesMonitor"
    )
}
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def format_24h(t_raw: str) -> str:
  t_raw = t_raw.strip().lower()
  is_pm = "pm" in t_raw
  is_am = "am" in t_raw
  m = re.search(r"(\d{1,2})[:.](\d{2})", t_raw)
  if not m:
    return ""
  hh = int(m.group(1))
  mm = m.group(2)
  if is_pm and hh < 12:
    hh += 12
  elif is_am and hh == 12:
    hh = 0
  return f"{hh:02d}:{mm}"


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
      community.replace("Glanrhyd (Penrallt)", "Moylegrove")
      .replace("St. Dogmaels", "St Dogmaels")
      .replace("St.Florence", "St Florence")
      .replace("St.Ishmaels", "St Ishmaels")
      .replace("St Twynnells", "St Twynnells")
      .replace("Hayscastle Cross", "Hayscastle")
      .replace("Simpson Cross", "Roch")
      .replace("Bwlch y Groes", "Clydey")
      .replace("Blaenffos", "Boncath")
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
        if p.get("county_unitary") == "Pembrokeshire" or (
            51.60 <= lat <= 52.12 and -5.35 <= lng <= -4.50
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

  default_coords = (51.8017, -4.9708)
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


def parse_pembrokeshire_html(html: str):
  soup = bs4.BeautifulSoup(html, "html.parser")
  lines = [
      l.replace("\xa0", " ").replace("\ufeff", "").strip()
      for l in soup.get_text("\n", strip=True).splitlines()
      if l.strip()
  ]
  stops = []
  current_route = ""
  current_day = ""

  for line in lines:
    m_route = re.match(r"^([A-H]):\s*(.+)$", line)
    if m_route:
      current_route = f"Route {m_route.group(1)}: {m_route.group(2).strip()}"
      continue
    if current_route:
      m_day = re.match(
          r"^(Monday|Tuesday|Wednesday|Thursday|Friday)\s+\d+", line, re.I
      )
      if m_day:
        current_day = m_day.group(1).title()
        continue
      m_stop = re.match(
          r"^(.+?)\s+(\d{1,2}[:.]\d{2}\s*(?:am|pm)?)\s*[-–]\s*(\d{1,2}[:.]\d{2}\s*(?:am|pm)?)$",
          line,
          re.I,
      )
      if m_stop and current_day:
        loc_raw = m_stop.group(1).strip()
        arr = format_24h(m_stop.group(2))
        dep = format_24h(m_stop.group(3))
        if "," in loc_raw:
          comm, stop_name = [p.strip() for p in loc_raw.split(",", 1)]
        else:
          comm = loc_raw
          stop_name = loc_raw
        stops.append({
            "route": current_route,
            "day": current_day,
            "community": comm,
            "stop": stop_name,
            "arr": arr,
            "dep": dep,
            "url": BASE_URL,
        })
  return stops


def run():
  print(f"[{SLUG}] Starting ingestion for {AUTHORITY_NAME} ({AUTHORITY_CODE})...")
  date_stamp = datetime.now().strftime("%Y-%m-%d")
  raw_dir = os.path.join("raw", SLUG, date_stamp)
  os.makedirs(raw_dir, exist_ok=True)

  html_path = os.path.join(raw_dir, "mobile_library.html")
  if not os.path.exists(html_path):
    req = urllib.request.Request(BASE_URL, headers=HEADERS)
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
      with open(html_path, "wb") as f:
        f.write(resp.read())

  with open(html_path, "r", encoding="utf-8", errors="replace") as f:
    html = f.read()

  geocache_path = os.path.join("geocache", "stops_reference.json")
  if os.path.exists(geocache_path):
    with open(geocache_path, "r", encoding="utf-8") as f:
      geocache = json.load(f)
  else:
    geocache = {}

  all_raw_stops = parse_pembrokeshire_html(html)
  print(f"[{SLUG}] Extracted {len(all_raw_stops)} stops across routes A-H")

  session_cache = {}
  pc_cache = {}
  stops_records = []
  vehicle = "Pembrokeshire Mobile Library"

  for s in all_raw_stops:
    comm = s["community"]
    stop_name = s["stop"]
    lat, lng = geocode_place(comm, stop_name, geocache, session_cache)
    postcode = reverse_geocode_postcode(lat, lng, pc_cache)

    geocache[f"{AUTHORITY_NAME}:{comm}:{stop_name}".lower()] = (lat, lng)
    if postcode:
      geocache[postcode] = (lat, lng)

    address = (
        f"{stop_name}, {comm}, Pembrokeshire"
        if stop_name.lower() != comm.lower()
        else f"{comm}, Pembrokeshire"
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
        "Start": "2026-10-01",
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
          "Notes": "Pembrokeshire 4-weekly village mobile library routes A-H",
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
        r["source_format"] = "HTML Timetable"
        r["last_checked"] = today
        r["last_updated"] = today
        r["notes"] = (
            f"Harvested {len(stops_records)} stops across 8 village routes"
            " (A-H) on a 4-week cycle."
        )
        break
    with open(services_csv, "w", encoding="utf-8", newline="") as f:
      writer = csv.DictWriter(f, fieldnames=s_fieldnames)
      writer.writeheader()
      writer.writerows(rows)


if __name__ == "__main__":
  run()
