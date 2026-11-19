"""
Carmarthenshire County Council Mobile Library Ingestion Script
Harvests the 60 mobile library stop pages from Carmarthenshire County Council:
https://www.carmarthenshire.gov.wales/home/council-services/libraries-archives/mobile-libraries/
Validates schema compliance and updates services.csv, geocache, historical stops, and historical vehicle registries.
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

AUTHORITY_NAME = "Carmarthenshire"
AUTHORITY_CODE = "W06000010"
SLUG = "carmarthenshire"

BASE_URL = "https://www.carmarthenshire.gov.wales/home/council-services/libraries-archives/mobile-libraries/"
DOMAIN = "https://www.carmarthenshire.gov.wales"

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

  clean_comm = re.sub(
      r"\s+(Square|Y Wesle|Ger-Y-Capel|Hall|Ger Y Marbell|Hen Gapel|1)$",
      "",
      community,
      flags=re.I,
  ).strip()
  clean_comm = (
      clean_comm.replace("Crosshands", "Cross Hands")
      .replace("Banc y felin", "Bancyfelin")
      .replace("Mynyddygarreg", "Mynydd-y-garreg")
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
        if p.get("county_unitary") == "Carmarthenshire" or (
            51.65 <= lat <= 52.15 and -4.65 <= lng <= -3.70
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

  default_coords = (51.8576, -4.3121)
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


def parse_stop_page(html: str, url: str):
  soup = bs4.BeautifulSoup(html, "html.parser")
  content = soup.find(id="content") or soup
  h1 = content.find("h1")
  if not h1:
    return None

  # Extract title and route subtitle
  span = h1.find("span", class_="small")
  route_str = "Route 1"
  if span:
    span_text = " ".join(span.get_text(" ", strip=True).split())
    route_str = f"Route {span_text}"
    span.extract()
  comm_title = " ".join(h1.get_text(" ", strip=True).split())

  dates_div = content.find("div", class_="mobileLibraryDates")
  if not dates_div:
    return None

  text_lines = [
      " ".join(p.get_text(" ", strip=True).split())
      for p in dates_div.find_all(["p", "li"])
  ]
  full_text = "\n".join(text_lines)

  # Find day & times e.g. "01/12/2026 ~ Tuesday 14:45 - 15:45"
  m_visit = re.search(
      r"(\d{2}/\d{2}/\d{4})\s*~\s*(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2}[:.]\d{2})\s*[-–]\s*(\d{1,2}[:.]\d{2})",
      full_text,
      re.I,
  )

  # Find Location
  loc_name = comm_title
  for p in dates_div.find_all("p"):
    ptxt = " ".join(p.get_text(" ", strip=True).split())
    if "Location:" in ptxt:
      loc_part = ptxt.split("Location:", 1)[1].strip()
      loc_part = re.sub(r"\s*View location.*$", "", loc_part, flags=re.I).strip()
      if " - " in loc_part:
        loc_name = loc_part.split(" - ", 1)[1].strip()
      elif loc_part:
        loc_name = loc_part

  if not m_visit:
    return {
        "active": False,
        "route": route_str,
        "community": comm_title,
        "stop": loc_name,
        "url": url,
    }

  date_str = m_visit.group(1)
  day_name = m_visit.group(2).title()
  arr = m_visit.group(3).replace(".", ":")
  dep = m_visit.group(4).replace(".", ":")
  if len(arr) == 4:
    arr = "0" + arr
  if len(dep) == 4:
    dep = "0" + dep

  # Calculate interval if future visit exists
  all_dates = re.findall(r"(\d{2}/\d{2}/\d{4})\s*~", full_text)
  interval = 3
  start_iso = "2026-11-20"
  try:
    dt0 = datetime.strptime(all_dates[0], "%d/%m/%Y")
    start_iso = dt0.strftime("%Y-%m-%d")
    if len(all_dates) >= 2:
      dt1 = datetime.strptime(all_dates[1], "%d/%m/%Y")
      diff_days = abs((dt1 - dt0).days)
      if diff_days >= 7 and diff_days % 7 == 0:
        interval = diff_days // 7
  except Exception:
    pass

  return {
      "active": True,
      "route": route_str,
      "day": day_name,
      "community": comm_title,
      "stop": loc_name,
      "arr": arr,
      "dep": dep,
      "freq": f"FREQ=WEEKLY;INTERVAL={interval}",
      "start": start_iso,
      "url": url,
  }


def run():
  print(f"[{SLUG}] Starting ingestion for {AUTHORITY_NAME} ({AUTHORITY_CODE})...")
  date_stamp = datetime.now().strftime("%Y-%m-%d")
  raw_dir = os.path.join("raw", SLUG, date_stamp)
  stops_raw_dir = os.path.join(raw_dir, "stops")
  os.makedirs(stops_raw_dir, exist_ok=True)

  index_path = os.path.join(raw_dir, "index.html")
  if not os.path.exists(index_path):
    req = urllib.request.Request(BASE_URL, headers=HEADERS)
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
      with open(index_path, "wb") as f:
        f.write(resp.read())

  with open(index_path, "r", encoding="utf-8", errors="replace") as f:
    index_html = f.read()

  soup = bs4.BeautifulSoup(index_html, "html.parser")
  stop_paths = sorted(
      set(
          a["href"]
          for a in soup.find_all("a", href=True)
          if "/home/council-services/libraries-archives/mobile-libraries/"
          in a["href"]
          and a["href"].rstrip("/")
          != "/home/council-services/libraries-archives/mobile-libraries"
      )
  )
  print(f"[{SLUG}] Found {len(stop_paths)} stop URLs on index page")

  geocache_path = os.path.join("geocache", "stops_reference.json")
  if os.path.exists(geocache_path):
    with open(geocache_path, "r", encoding="utf-8") as f:
      geocache = json.load(f)
  else:
    geocache = {}

  active_stops = []
  unscheduled_stops = []

  for spath in stop_paths:
    stop_slug = spath.rstrip("/").split("/")[-1]
    full_url = DOMAIN + spath
    local_file = os.path.join(stops_raw_dir, f"{stop_slug}.html")
    if not os.path.exists(local_file):
      for attempt in range(3):
        try:
          req = urllib.request.Request(full_url, headers=HEADERS)
          with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
            with open(local_file, "wb") as f:
              f.write(resp.read())
          break
        except Exception:
          import time

          time.sleep(1.5)
    if not os.path.exists(local_file):
      continue
    with open(local_file, "r", encoding="utf-8", errors="replace") as f:
      shtml = f.read()
    parsed = parse_stop_page(shtml, full_url)
    if parsed:
      if parsed["active"]:
        active_stops.append(parsed)
      else:
        unscheduled_stops.append(parsed)

  print(
      f"[{SLUG}] Parsed {len(active_stops)} active stops and"
      f" {len(unscheduled_stops)} unscheduled stops"
  )

  session_cache = {}
  pc_cache = {}
  stops_records = []
  vehicle = "Carmarthenshire Mobile Library"

  for s in active_stops:
    comm = s["community"]
    stop_name = s["stop"]
    lat, lng = geocode_place(comm, stop_name, geocache, session_cache)
    postcode = reverse_geocode_postcode(lat, lng, pc_cache)

    geocache[f"{AUTHORITY_NAME}:{comm}:{stop_name}".lower()] = (lat, lng)
    if postcode:
      geocache[postcode] = (lat, lng)

    address = (
        f"{stop_name}, {comm}, Carmarthenshire"
        if stop_name.lower() != comm.lower()
        else f"{comm}, Carmarthenshire"
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
        "Frequency": s["freq"],
        "Start": s["start"],
        "End": "2027-03-31",
        "Exceptions": "Bank holidays",
        "Timetable": s["url"],
    })

  stops_records.sort(key=lambda r: (r["Route"], r["Arrival"], r["Community"]))

  # Archive unscheduled stops to history/historical_mobile_stops.csv
  hist_stops_csv = os.path.join("history", "historical_mobile_stops.csv")
  if unscheduled_stops and os.path.exists(hist_stops_csv):
    with open(hist_stops_csv, "r", encoding="utf-8") as f:
      reader = csv.DictReader(f)
      h_fields = reader.fieldnames
      h_rows = list(reader)
    existing_h = {
        (r.get("Local authority"), r.get("Community"), r.get("Stop"))
        for r in h_rows
    }
    h_added = 0
    for u in unscheduled_stops:
      comm = u["community"]
      stop_name = u["stop"]
      if (AUTHORITY_NAME, comm, stop_name) not in existing_h:
        lat, lng = geocode_place(comm, stop_name, geocache, session_cache)
        postcode = reverse_geocode_postcode(lat, lng, pc_cache)
        h_rows.append({
            "Local authority": AUTHORITY_NAME,
            "Local authority code": AUTHORITY_CODE,
            "Mobile name": vehicle,
            "Route": u["route"],
            "Community": comm,
            "Stop": stop_name,
            "Address": f"{stop_name}, {comm}, Carmarthenshire",
            "Postcode": postcode,
            "GeoX": lng,
            "GeoY": lat,
            "Day": "",
            "Type": "Public",
            "Arrival": "",
            "Departure": "",
            "Frequency": "FREQ=WEEKLY;INTERVAL=3",
            "Start": "",
            "Dataset slug": SLUG,
            "Archive source": u["url"],
            "Status": "Suspended / Unscheduled",
        })
        h_added += 1
    if h_added > 0:
      with open(hist_stops_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=h_fields)
        writer.writeheader()
        writer.writerows(h_rows)

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
              "Carmarthenshire 3-weekly rural mobile library service with Wi-Fi"
              " hotspot"
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
        r["source_url"] = BASE_URL
        r["source_format"] = "HTML Stop Pages"
        r["last_checked"] = today
        r["last_updated"] = today
        r["notes"] = (
            f"Harvested {len(stops_records)} active stops (plus"
            f" {len(unscheduled_stops)} unscheduled archived to history) across"
            " 3-weekly routes."
        )
        break
    with open(services_csv, "w", encoding="utf-8", newline="") as f:
      writer = csv.DictWriter(f, fieldnames=s_fieldnames)
      writer.writeheader()
      writer.writerows(rows)


if __name__ == "__main__":
  run()
