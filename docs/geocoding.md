# Location and map coordinates

This guide explains how mobile library stop locations are found, how accurate they are, and how to improve them.

## Levels of accuracy

Depending on the information published by the council, stops fall into one of four accuracy levels:

* **Exact stop (within 1 to 10 metres):** The actual parking bay, layby, or school gate from council GIS maps or manual checks.
* **Named building (within 10 to 30 metres):** The physical building named in the timetable (such as a village hall or school).
* **Postcode centre (within 50 to 200 metres):** The geographic centre of the postcode.
* **Community centre (within 500 metres to 2 kilometres):** The village or settlement centre, used when a council only publishes a village name.

Currently, across all 8,284 stops in the UK dataset:
* **Postcode centre:** 42.1% (3,487 stops)
* **Exact stop / council GIS:** 34.6% (2,863 stops)
* **Named building / landmark:** 23.3% (1,934 stops)
* **Community centre fallback:** 0.0% (0 stops)

100% of all stops across the UK are mapped to an exact stop, physical building, or postcode.

Coordinates are stored to 5 decimal places (e.g. `53.02340`, `-3.56120`), which gives about 1-metre precision on the ground.

Each council also has a boundary box in `geocache/authority_bboxes.json` to ensure coordinates stay within the right area.

## How coordinates are resolved

When a script runs, it looks for coordinates in this order:

1. **Manual pins (`geocache/manual_pins.json`):** Manually checked stops that are permanently locked against automated changes.
2. **Saved reference stops (`geocache/stops_reference.json`):** Previously checked stops.
3. **Council map layers:** Interactive GIS maps and map servers.
4. **OpenStreetMap search:** Matching named buildings and streets via `scripts/upgrade_coordinates.py`.
5. **Postcode lookup:** Postcode centroids from Postcodes.io.
6. **Community lookup:** Village centre fallbacks from Postcodes.io.

## Upgrading coordinates automatically

To search OpenStreetMap for named buildings (schools, village halls, pubs) and streets that currently have rough village coordinates:

```bash
# Upgrade stops for one council
python scripts/upgrade_coordinates.py --authority leicestershire --limit 50

# Run across all councils
python scripts/upgrade_coordinates.py --all --limit 100
```

Matches are checked against the council boundary, saved to the council CSV, and cached.

## Checking and updating coordinates manually

You can review stops on Street View and lock in exact coordinates so automated scripts never overwrite them:

### 1. Export the review queue

```bash
python scripts/manual_geocode.py --export-queue
```

This creates `data/geocoding_review_queue.csv` sorted by priority (rough village centres first), with direct Google Maps and Street View links for each stop.

### 2. Import completed coordinates

After adding coordinates in the spreadsheet:

```bash
python scripts/manual_geocode.py --import-queue data/geocoding_review_queue.csv
```

This updates the council CSV and saves the coordinates to `geocache/manual_pins.json`.

### 3. Update a single stop directly

```bash
python scripts/manual_geocode.py --update --authority conwy --community "Capel Curig" --stop "Caffi Siabod" --lat 53.10264 --lon -3.90615 --notes "Checked on Street View"
```

## Accuracy dataset and map files

* **`data/uk_mobile_library_stops_accuracy.csv`**: Lists every stop with its accuracy level (`exact`, `landmark`, `postcode`, or `community`), estimated error radius, and verification status.
* **`data/uk_mobile_library_stops.geojson`**: Includes accuracy properties on every map pin for styling in GIS or web maps.
