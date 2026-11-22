# How to run the scripts

This guide explains how to collect timetable data for a council, combine all stops into a single UK file, and work out driving routes.

## 1. Updating data for a council

Each council that runs a mobile library has its own Python script in the `scripts/` folder.

Running the script visits the council's website or downloads their published timetable, works out the map coordinates, and saves the results in `data/<council>.csv`:

```bash
# Run a specific council script
python scripts/conwy.py
python scripts/leicestershire.py
python scripts/highland.py
```

What the script does:
* Downloads the council's timetable (from a webpage, PDF leaflet, or council database).
* Saves a copy of the original timetable in `raw/<council>/<date>/` so we have a record.
* Converts times into the standard 24-hour clock (like `10:15`).
* Works out map coordinates for each stop to 5 decimal places.
* Checks the file to make sure it matches the required standard.

## 2. Combining all stops into a single UK file

To merge all individual council files into one nationwide dataset, run:

```bash
python scripts/combine.py
```

This updates two files in the `data/` folder:
* **`data/uk_mobile_library_stops.csv`**: A single spreadsheet containing all 8,100+ stops across the UK.
* **`data/uk_mobile_library_stops.geojson`**: A map file that can be opened in mapping tools (such as QGIS, ArcGIS, or web map viewers) to see every stop as a pin on a map.

## 3. Calculating driving routes between stops

To work out the road path and driving time between consecutive stops on each route:

```bash
# Calculate routes for a single council
python scripts/routing.py --authority shropshire

# Calculate routes for all councils
python scripts/routing.py --all

# Force the script to recalculate routes that already exist
python scripts/routing.py --authority somerset --force
```

By default, the script uses the free OpenStreetMap road network (OSRM) with no setup required.

All route files are saved in `data/routes/`. For more information, see [driving routes between stops](routing.md).

## 4. Improving stop coordinates

To improve coordinates automatically or check uncertain stops on Street View:

```bash
# Search OpenStreetMap for named buildings and streets
python scripts/upgrade_coordinates.py --authority leicestershire --limit 50

# Export stops sorted by review priority with Street View links
python scripts/manual_geocode.py --export-queue

# Import verified coordinates from the spreadsheet
python scripts/manual_geocode.py --import-queue data/geocoding_review_queue.csv

# Update a single stop directly
python scripts/manual_geocode.py --update --authority conwy --community "Capel Curig" --stop "Caffi Siabod" --lat 53.10264 --lon -3.90615 --notes "Checked on Street View"
```

For full details on accuracy levels and the verification process, see [location and map coordinates](geocoding.md).
