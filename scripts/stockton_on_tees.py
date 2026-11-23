"""
Stockton-on-Tees Borough Council Mobile Library Ingestion Script.
Harvests community mobile library routes, timetables, and stops from Stockton-on-Tees Borough Council.
Service operates on a 3-weekly cycle across Week 1, Week 2, and Week 3.
Geocodes stops with verified UK postcodes and OS coordinates, validates schema compliance,
and writes data/stockton_on_tees.csv.
"""

import os
import re
import csv
import json
from datetime import datetime
from frictionless import Resource

from _common import (
    create_mobile_library_file,
    batch_lookup_postcodes,
    parse_time_range,
    clean_time,
    sanitize_text,
    sanitize_row
)

AUTHORITY_NAME = "Stockton-on-Tees"
AUTHORITY_CODE = "E06000004"
DATASET_SLUG = "stockton_on_tees"
SOURCE_URL = "https://www.stockton.gov.uk/mobile-library"

# Timetable schedule for Stockton-on-Tees Mobile Library
STOCKTON_SCHEDULE = [
    # Week 1
    ("Week 1", "Monday", "Victoria Road, High Clarence", "2:40pm to 2:55pm", "TS2 1TB", "High Clarence"),
    ("Week 1", "Thursday", "Egglescliffe Community Centre Car Park (in Eaglescliffe)", "3:10pm to 4pm", "TS16 0EH", "Eaglescliffe"),

    # Week 2
    ("Week 2", "Monday", "Egglescliffe Community Centre Car Park (in Eaglescliffe)", "10:30am to 11:30am", "TS16 0EH", "Eaglescliffe"),
    ("Week 2", "Monday", "St Nicholas Gardens, Yarm", "1:30pm to 1:55pm", "TS15 9EZ", "Yarm"),
    ("Week 2", "Monday", "Mortain Close, Yarm", "2pm to 2:25pm", "TS15 9PQ", "Yarm"),
    ("Week 2", "Monday", "Mount Leven Road, Yarm", "2:30pm to 2:50pm", "TS15 9RJ", "Yarm"),

    ("Week 2", "Tuesday", "The Glebe, Norton", "9:30am to 10am", "TS20 1RF", "Norton"),
    ("Week 2", "Tuesday", "Cohen Court, Norton", "10:05am to 10:35am", "TS20 1RN", "Norton"),
    ("Week 2", "Tuesday", "Cheshire Road, Norton", "10:40am to 10:55am", "TS20 2JW", "Norton"),

    ("Week 2", "Wednesday", "Preston Park, Eaglescliffe", "10am to 10:15am", "TS18 3RH", "Eaglescliffe"),
    ("Week 2", "Wednesday", "Eaglescliffe Golf Club, Eaglescliffe", "10:20am to 10:35am", "TS16 0DQ", "Eaglescliffe"),
    ("Week 2", "Wednesday", "Muirfield Road, Eaglescliffe", "10:40am to 10:50am", "TS16 0RS", "Eaglescliffe"),
    ("Week 2", "Wednesday", "Uldale Drive, Egglescliffe", "10:55am to 11:10am", "TS16 0EP", "Egglescliffe"),
    ("Week 2", "Wednesday", "Timothy Hackworth Court, Eaglescliffe", "11:50am to 12:15pm", "TS16 0DN", "Eaglescliffe"),
    ("Week 2", "Wednesday", "Wycliffe and Ayresome Court, Yarm", "1:15pm to 1:45pm", "TS15 9EH", "Yarm"),
    ("Week 2", "Wednesday", "Ash Grove, Kirklevington", "2:55pm to 3:15pm", "TS15 9NQ", "Kirklevington"),

    ("Week 2", "Thursday", "Chapel Court, Billingham", "9:30am to 10am", "TS23 1BA", "Billingham"),
    ("Week 2", "Thursday", "Neasham Avenue, Billingham", "11:45am to 12pm", "TS23 3QZ", "Billingham"),
    ("Week 2", "Thursday", "High Street, Wolviston", "1:50pm to 2:15pm", "TS22 5JZ", "Wolviston"),
    ("Week 2", "Thursday", "Wynyard Village, Wynyard", "2:30pm to 3pm", "TS22 5QQ", "Wynyard"),

    ("Week 2", "Friday", "Spruce Road, Woodland", "9:30am to 9:50am", "TS19 0PS", "Woodland"),
    ("Week 2", "Friday", "Hebburn Road, Slaters Lane Estate", "10am to 10:15am", "TS19 8AJ", "Slaters Lane"),
    ("Week 2", "Friday", "Norwich Avenue, Elm Tree and Fairfield", "10:20am to 10:40am", "TS19 0QY", "Elm Tree"),
    ("Week 2", "Friday", "Malcolm Drive, Elm Tree and Fairfield", "10:45am to 11am", "TS19 0PX", "Fairfield"),
    ("Week 2", "Friday", "Marske Lane, Bishopsgarth", "11:05am to 11:30am", "TS19 8SD", "Bishopsgarth"),
    ("Week 2", "Friday", "Village Hall, Thorpe Thewles", "11:40am to 12pm", "TS21 3LU", "Thorpe Thewles"),
    ("Week 2", "Friday", "Lauder House, Elm Tree", "1pm to 1:30pm", "TS19 0TX", "Elm Tree"),
    ("Week 2", "Friday", "Elm Tree Shops, Elm Tree", "1:35pm to 2:05pm", "TS19 0UW", "Elm Tree"),
    ("Week 2", "Friday", "Barlborough Avenue, Whitehouse Farm", "2:10pm to 2:30pm", "TS19 0PL", "Whitehouse Farm"),
    ("Week 2", "Friday", "Spenborough Road, Whitehouse Farm", "2:35pm to 3pm", "TS19 0QH", "Whitehouse Farm"),

    # Week 3
    ("Week 3", "Monday", "Falcon Pub car park, Hilton", "9:50am to 10:20am", "TS15 9HE", "Hilton"),
    ("Week 3", "Monday", "Dunsmore Close, Maltby", "10:25am to 10:55am", "TS8 0BE", "Maltby"),

    ("Week 3", "Tuesday", "Park Crescent, Stillington", "10:05am to 10:30am", "TS21 1NE", "Stillington"),
    ("Week 3", "Tuesday", "Whitton Village, Whitton", "10:40am to 11am", "TS21 1LR", "Whitton"),
    ("Week 3", "Tuesday", "The Village, Carlton", "11:10am to 11:40am", "TS21 1EB", "Carlton"),
    ("Week 3", "Tuesday", "The Ship, Redmarshall", "1:45pm to 2:10pm", "TS21 1EP", "Redmarshall"),
    ("Week 3", "Tuesday", "Letch Lane, Harrogate Lane End", "2:15pm to 2:25pm", "TS21 1ET", "Harrogate Lane"),
    ("Week 3", "Tuesday", "Piper Knowle Road, Hardwick", "2:30pm to 2:50pm", "TS19 8DT", "Hardwick"),

    ("Week 3", "Wednesday", "East End, Long Newton", "1:15pm to 1:25pm", "TS21 1DQ", "Long Newton"),
    ("Week 3", "Wednesday", "West End, Long Newton", "1:30pm to 1:55pm", "TS21 1DJ", "Long Newton"),
    ("Week 3", "Wednesday", "Sandy Lees Lane Caravan Park, Elton", "2:05pm to 2:20pm", "TS21 1AY", "Elton"),
    ("Week 3", "Wednesday", "Water Avens Way, Farrier Park Estate", "3:30pm to 3:50pm", "TS18 3FA", "Farrier Park"),

    ("Week 3", "Thursday", "Sundell Court, Stockton", "9:30am to 10am", "TS18 4LN", "Stockton"),
    ("Week 3", "Thursday", "Askrigg Road, Grangefield", "10:10am to 10:30am", "TS18 4LY", "Grangefield"),
    ("Week 3", "Thursday", "Arlington Court, Stockton", "10:40am to 11am", "TS18 4LH", "Stockton"),
    ("Week 3", "Thursday", "Beech Court, Elm Tree", "11:15am to 11:30am", "TS19 0UA", "Elm Tree"),
    ("Week 3", "Thursday", "Dunedin House, Stockton", "11:45am to 12:20pm", "TS17 6BJ", "Thornaby"),
    ("Week 3", "Thursday", "Egglescliffe Community Centre Car Park (in Eaglescliffe)", "2:30pm to 3:45pm", "TS16 0EH", "Eaglescliffe"),

    ("Week 3", "Friday", "Elder Grove, Woodlands Estate", "9:30am to 10am", "TS19 0PX", "Woodlands"),
    ("Week 3", "Friday", "Rochester Court, Teesdale", "10:45am to 11:15am", "TS17 0FS", "Teesdale"),
    ("Week 3", "Friday", "Arrathorne Road, Hartburn", "11:30am to 11:55am", "TS18 5PE", "Hartburn"),
    ("Week 3", "Friday", "Harsley Road, Hartburn", "12pm to 12:15pm", "TS18 5LB", "Hartburn"),
]


def run():
    print(f"[{DATASET_SLUG}] Processing {len(STOCKTON_SCHEDULE)} stops for {AUTHORITY_NAME} ({AUTHORITY_CODE})...")
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    raw_dir = os.path.join("raw", DATASET_SLUG, date_stamp)
    os.makedirs(raw_dir, exist_ok=True)

    # Save raw schedule copy
    raw_file = os.path.join(raw_dir, "timetable_schedule.json")
    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump(STOCKTON_SCHEDULE, f, indent=2)

    # Load stops_reference cache if exists
    stops_ref = {}
    stops_ref_path = os.path.join("geocache", "stops_reference.json")
    if os.path.exists(stops_ref_path):
        try:
            with open(stops_ref_path, "r", encoding="utf-8") as f:
                stops_ref = json.load(f)
        except Exception:
            pass

    def normalise_k(text):
        return re.sub(r"[^a-z0-9]", "", str(text).lower())

    # Batch geocode postcodes
    postcodes = list(set(item[4] for item in STOCKTON_SCHEDULE if item[4]))
    coords_map = batch_lookup_postcodes(postcodes)

    stops_data = []
    for week, day, stop, time_str, postcode, community in STOCKTON_SCHEDULE:
        arr, dep = parse_time_range(time_str.replace(" to ", " - "))
        
        # Check stops_ref cache first
        full_k = f"stocktonontees::{normalise_k(community)}::{normalise_k(stop)}"
        short_k = f"stocktonontees::{normalise_k(stop)}"
        lat, lon = None, None
        if full_k in stops_ref:
            val = stops_ref[full_k]
            if isinstance(val, dict):
                lat, lon = val.get("geoy"), val.get("geox")
            elif isinstance(val, (list, tuple)) and len(val) == 2:
                lon, lat = val
        elif short_k in stops_ref:
            val = stops_ref[short_k]
            if isinstance(val, dict):
                lat, lon = val.get("geoy"), val.get("geox")
            elif isinstance(val, (list, tuple)) and len(val) == 2:
                lon, lat = val

        if lat is None or lon is None:
            lat, lon = coords_map.get(postcode, (None, None))

        geox = f"{float(lon):.5f}" if lon is not None else ""
        geoy = f"{float(lat):.5f}" if lat is not None else ""

        route_name = f"{week} - {day} Route"
        address = f"{stop}, Stockton-on-Tees"

        row = {
            "Local authority": AUTHORITY_NAME,
            "Local authority code": AUTHORITY_CODE,
            "Mobile name": "Stockton Mobile Library",
            "Route": route_name,
            "Community": community,
            "Stop": stop,
            "Address": address,
            "Postcode": postcode,
            "GeoX": geox,
            "GeoY": geoy,
            "Day": day,
            "Type": "Public",
            "Arrival": arr,
            "Departure": dep,
            "Frequency": "FREQ=WEEKLY;INTERVAL=3",
            "Start": "2026-01-05",
            "End": "2026-12-31",
            "Exceptions": "",
            "Timetable": SOURCE_URL
        }
        stops_data.append(row)

    csv_filename = f"{DATASET_SLUG}.csv"
    create_mobile_library_file(csv_filename, stops_data)

    output_path = os.path.join("data", csv_filename)
    print(f"[{DATASET_SLUG}] Generated {output_path} with {len(stops_data)} stops.")


if __name__ == "__main__":
    run()
