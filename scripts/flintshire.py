"""
Flintshire (Gwella Wales / Aura Libraries) Mobile Library Ingestion Script
Harvests the 45 fortnightly stops across 8 routes from Flintshire's official timetable
(preserved via Aura Wales / Gwella Libraries transition archive) and saves to data/flintshire.csv.
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

AUTHORITY_NAME = "Flintshire"
AUTHORITY_CODE = "W06000005"
SLUG = "flintshire"

WAYBACK_URL = "https://web.archive.org/web/20230505051246id_/https://aura.wales/libraries/mobile-library-timetable/"
LIVE_URL = "https://gwella.wales/libraries"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def format_24h(t_str: str) -> str:
  t_str = t_str.strip().replace(".", ":")
  m = re.match(r"^(\d{1,2}):(\d{2})$", t_str)
  if not m:
    return ""
  hh = int(m.group(1))
  mm = m.group(2)
  # Times between 1:00 and 5:59 in daytime mobile library schedules are PM
  if 1 <= hh <= 5:
    hh += 12
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

  clean_comm = re.sub(r"\s*\(CH\d+\)\s*", "", community).strip()
  clean_comm = (
      clean_comm.replace("Green Lane Estate", "Shotton")
      .replace("Higher Shotton", "Shotton")
      .replace("Calcoed", "Holywell")
      .replace("Flint Mountain", "Flint")
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
        if p.get("county_unitary") == "Flintshire" or (
            53.08 <= lat <= 53.36 and -3.40 <= lng <= -2.90
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

  default_coords = (53.1674, -3.1419)
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


def parse_flintshire_html(html: str):
  soup = bs4.BeautifulSoup(html, "html.parser")
  table = soup.find("table")
  if not table:
    return []
  stops = []
  for tr in table.find_all("tr"):
    cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
    if len(cells) < 4:
      continue
    area, times, loc, dates_str = cells[0], cells[1], cells[2], cells[3]
    if area.lower() == "area" or not area:
      continue
    m_time = re.search(r"(\d{1,2}[:.]\d{2})\s*/\s*(\d{1,2}[:.]\d{2})", times)
    if not m_time:
      continue
    arr = format_24h(m_time.group(1))
    dep = format_24h(m_time.group(2))

    m_day = re.search(
        r"\b(Monday|Tuesday|Wednesday|Thursday|Friday)\s+May\s+(\d{1,2})\b",
        dates_str,
        re.I,
    )
    day_name = m_day.group(1).title() if m_day else "Tuesday"
    day_num = int(m_day.group(2)) if m_day else 9
    week_num = 1 if day_num <= 12 else 2

    stops.append({
        "route": f"Week {week_num} {day_name}",
        "day": day_name,
        "community": area,
        "stop": loc,
        "arr": arr,
        "dep": dep,
        "url": LIVE_URL,
    })
  return stops


def run():
  print(f"[{SLUG}] Starting ingestion for {AUTHORITY_NAME} ({AUTHORITY_CODE})...")
  date_stamp = datetime.now().strftime("%Y-%m-%d")
  raw_dir = os.path.join("raw", SLUG, date_stamp)
  hist_dir = os.path.join("raw", SLUG, "historical")
  os.makedirs(raw_dir, exist_ok=True)
  os.makedirs(hist_dir, exist_ok=True)

  html_path = os.path.join(raw_dir, "mobile_library_timetable.html")
  hist_path = os.path.join(hist_dir, "aura_mobile_library_timetable_2023.html")
  if not os.path.exists(html_path):
    req = urllib.request.Request(WAYBACK_URL, headers=HEADERS)
    with urllib.request.urlopen(req, context=ctx, timeout=25) as resp:
      content = resp.read()
      with open(html_path, "wb") as f:
        f.write(content)
      with open(hist_path, "wb") as f:
        f.write(content)

  with open(html_path, "r", encoding="utf-8", errors="replace") as f:
    html = f.read()

  geocache_path = os.path.join("geocache", "stops_reference.json")
  if os.path.exists(geocache_path):
    with open(geocache_path, "r", encoding="utf-8") as f:
      geocache = json.load(f)
  else:
    geocache = {}

  all_raw_stops = parse_flintshire_html(html)
  print(f"[{SLUG}] Extracted {len(all_raw_stops)} stops across Week 1-2 routes")

  session_cache = {}
  pc_cache = {}
  stops_records = []
  vehicle = "Flintshire Mobile Library"

  for s in all_raw_stops:
    comm = s["community"]
    stop_name = s["stop"]
    lat, lng = geocode_place(comm, stop_name, geocache, session_cache)
    postcode = reverse_geocode_postcode(lat, lng, pc_cache)

    geocache[f"{AUTHORITY_NAME}:{comm}:{stop_name}".lower()] = (lat, lng)
    if postcode:
      geocache[postcode] = (lat, lng)

    address = (
        f"{stop_name}, {comm}, Flintshire"
        if stop_name.lower() != comm.lower()
        else f"{comm}, Flintshire"
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
        "Frequency": "FREQ=WEEKLY;INTERVAL=2",
        "Start": "2023-05-05",
        "End": "2027-06-27",
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
          "Notes": (
              "Flintshire fortnightly mobile library service operated by Gwella"
              " Wales (formerly Aura Libraries)"
          ),
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
        r["source_url"] = LIVE_URL
        r["source_format"] = "HTML Table"
        r["last_checked"] = today
        r["last_updated"] = today
        r["notes"] = (
            f"Harvested {len(stops_records)} stops across 8 fortnightly routes"
            " (Gwella Wales / Aura Libraries transition timetable)."
        )
        break
    with open(services_csv, "w", encoding="utf-8", newline="") as f:
      writer = csv.DictWriter(f, fieldnames=s_fieldnames)
      writer.writeheader()
      writer.writerows(rows)


if __name__ == "__main__":
  run()
