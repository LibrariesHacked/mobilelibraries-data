# Driving routes between stops

This guide explains how we calculate the driving path, distance, and travel time between consecutive stops on a mobile library route.

## How routes are calculated

Mobile library vehicles travel on public roads between scheduled stops. Rather than drawing straight lines through the air, our routing script [`scripts/routing.py`](../scripts/routing.py) works out the actual driving path along the road network.

* **Driving order:** Stops on each route are automatically sorted by their scheduled arrival time, so the path follows the van's real journey through the day.
* **Travel measurements:** The script measures the driving distance in metres and the estimated driving time in seconds between each stop.

## Routing services

The script can use two routing providers:

1. **OSRM (open default):**
   * Uses live OpenStreetMap road network data.
   * Free and requires no account or API key.
2. **OpenRouteService (lorry / HGV profile):**
   * Uses commercial vehicle rules to avoid roads with low bridges, narrow lanes, or weight restrictions.
   * Requires a free API key from [openrouteservice.org](https://openrouteservice.org/). To use it, set the key in your terminal as `ORS_API_KEY`.

## How to run the routing script

You can work out routes from your terminal:

```bash
# Calculate routes for a single council
python scripts/routing.py --authority shropshire

# Calculate routes for all councils
python scripts/routing.py --all

# Force the script to recalculate routes that already exist
python scripts/routing.py --authority somerset --force
```

## Where route files are saved

All route files are saved in the `data/routes/` folder:

* **`data/routes/<council>_routes.csv`**: A spreadsheet of journeys between stops. Each row shows the starting stop, destination stop, driving distance, driving time, and the road line geometry.
* **`data/routes/<council>_routes.geojson`**: A map file that can be opened in mapping tools (like QGIS or web maps) to display the road lines visually.
