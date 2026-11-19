"""
Common functions for mobile library data output and schema validation.
Conforms to LibrariesHacked schema-librarydata/mobile-library-stops.json
"""

import csv
from datetime import datetime
from pathlib import Path

DATA_OUTPUT = Path(__file__).resolve().parent.parent / 'data'
SCHEMA_PATH = Path(__file__).resolve().parent.parent / 'schemas' / 'mobile-library-stops.json'

SCHEMA_COLUMNS = [
    'Local authority',
    'Local authority code',
    'Mobile name',
    'Route',
    'Community',
    'Stop',
    'Address',
    'Postcode',
    'GeoX',
    'GeoY',
    'Day',
    'Type',
    'Arrival',
    'Departure',
    'Frequency',
    'Start',
    'End',
    'Exceptions',
    'Timetable'
]


def create_mobile_library_file(filename, stops):
    """
    Writes stops into a standard CSV file adhering to mobile-library-stops.json.
    Stops can be either a list of dicts (keyed by column name) or list of tuples/lists
    matching SCHEMA_COLUMNS order.
    """
    output_path = DATA_OUTPUT / filename
    DATA_OUTPUT.mkdir(parents=True, exist_ok=True)

    normalized_stops = []
    for item in stops:
        if isinstance(item, dict):
            row = [item.get(col, '') for col in SCHEMA_COLUMNS]
        else:
            row = list(item)
        normalized_stops.append(row)

    # Sort by Mobile name (index 2), Route (index 3), and Arrival time (index 12)
    def sort_key(row):
        mobile = str(row[2])
        route = str(row[3])
        time_str = str(row[12]).strip()
        # Normalise H:MM or HH:MM
        if '.' in time_str:
            parts = time_str.split('.')
            time_str = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        elif ':' in time_str:
            parts = time_str.split(':')
            time_str = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        else:
            time_str = '00:00'
        return (mobile, route, time_str)

    normalized_stops = sorted(normalized_stops, key=sort_key)

    with open(output_path, 'w', encoding='utf-8', newline='') as out_csv:
        writer = csv.writer(out_csv, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(SCHEMA_COLUMNS)
        for row in normalized_stops:
            writer.writerow(row)

    print(f"Written {len(normalized_stops)} stops to {output_path}")
