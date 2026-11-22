# Driving routes between stops

This guide explains how we calculate the driving path, distance, and travel time between consecutive stops on a mobile library route.

## How routes are calculated

Mobile library vehicles travel on public roads between scheduled stops. Rather than drawing straight lines through the air, our routing script [`scripts/routing.py`](../scripts/routing.py) works out the actual driving path along the road network.

* **Driving order:** Stops on each route are automatically sorted by their scheduled arrival time, so the path follows the van's real journey through the day.
* **Travel measurements:** The script measures the driving distance in metres and the estimated driving time in seconds between each stop.
* **Efficient change detection:** The script checks the coordinates on each route against existing route files. If no stop coordinates have changed on that route, it reuses the existing geometry, only requesting new road paths for routes where a stop has actually moved.

## Official council route polylines

When a local authority provides official route geometry (such as an ArcGIS or GIS FeatureServer layer published by the council), we prioritise those authoritative polylines over synthetic routing engine approximations:

1. **Storage location:** Official route files are saved in [`data/routes/official/<council>_official_routes.geojson`](../data/routes/official/) and dated raw copies in `raw/<council>/<date>/official_routes.json`.
2. **Automatic detection:** [`scripts/routing.py`](../scripts/routing.py) checks whether an official file exists for the authority. If found, it uses the council's official route line for the GeoJSON features and slices the polyline between consecutive stops to generate the trip rows in `<council>_routes.csv`.
3. **Trip calculations:** For official polylines, inter-stop distances are measured along the official line using the haversine formula, and driving durations are calculated from average speed or scheduled stop intervals.
4. **Metadata tagging:** Every routed feature and trip derived from official sources is explicitly marked with `"source": "official"`.
5. **Fallback:** If an individual route is not present in the official file, the script falls back to OSRM to calculate the road connection. To bypass official files and force synthetic routing for testing, use the `--force-engine` flag.

## Routing services

When official polylines are not provided by a council, the script uses a routing provider:

1. **OSRM (open default):**
   * Uses live OpenStreetMap road network data.
   * Free and requires no account or API key.
   * You can point the script to a custom or local OSRM instance using `--osrm-url` or the `OSRM_URL` environment variable (for example, `http://localhost:5000/route/v1/driving`).
2. **OpenRouteService (lorry / HGV profile):**
   * Uses commercial vehicle rules to avoid roads with low bridges, narrow lanes, or weight restrictions.
   * Requires a free API key from [openrouteservice.org](https://openrouteservice.org/). To use it, set the key in your terminal as `ORS_API_KEY`.

## How to run the routing script

You can work out routes from your terminal:

```bash
# Calculate routes for a single council (automatically using official polylines if available)
python scripts/routing.py --authority lancashire

# Calculate routes for all councils and combine into UK files
python scripts/routing.py --all

# Combine existing council route files into UK datasets
python scripts/routing.py --combine

# Force the script to recalculate routes that already exist
python scripts/routing.py --authority somerset --force

# Force synthetic OSRM routing even if official polylines exist
python scripts/routing.py --authority lancashire --force-engine
```

## Where route files are saved

All individual council route files are stored in `data/routes/`:

* **`data/routes/official/<council>_official_routes.geojson`**: Authoritative route line geometries provided directly by local council GIS services (e.g. Lancashire).
* **`data/routes/<council>_routes.csv`**: A spreadsheet of journeys between stops for that council. Each row shows the starting stop, destination stop, driving distance, driving time, and the road line geometry.
* **`data/routes/<council>_routes.geojson`**: A map file that can be opened in mapping tools (like QGIS or web maps) to display the road lines visually.

All council routes are also combined into single nationwide files:

* **`data/uk_mobile_library_routes.csv`**: All 6,941 scheduled road trip legs across all 48 UK mobile library services.
* **`data/uk_mobile_library_routes.geojson`**: Compact GeoJSON file containing all 1,160 route line geometries for the entire UK.
