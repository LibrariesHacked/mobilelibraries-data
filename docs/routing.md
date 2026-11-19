# Route Geometry Generation

This repository includes a routing engine in [`scripts/routing.py`](../scripts/routing.py) that generates realistic road geometries and travel estimates between consecutive stops on mobile library routes.

---

## 1. Routing Engines & Technology

Mobile libraries travel on public roads between scheduled stops. The routing engine supports two providers:

1. **OpenRouteService (ORS):**
   - **Profile:** `driving-hgv` (Heavy Goods Vehicle restrictions: weight, height, axle limits).
   - **Authentication:** Requires `ORS_API_KEY` environment variable.
2. **Open Source Routing Machine (OSRM):**
   - **Profile:** Standard driving road network based on live OpenStreetMap data.
   - **Authentication:** None required (zero-config open fallback).

### Chronological Waypoint Sequencing
Before generating directions, stops on each route schedule are automatically sorted chronologically by scheduled `Arrival` time. This guarantees that road geometries follow the true driving sequence rather than arbitrary timetable order.

---

## 2. Running the Routing Engine

### Using OpenRouteService (HGV Profile)
1. Register at [openrouteservice.org/sign-up](https://openrouteservice.org/sign-up).
2. Set your API key:
   - **Linux / macOS:** `export ORS_API_KEY="your-api-key"`
   - **Windows (PowerShell):** `$env:ORS_API_KEY="your-api-key"`

### Using OSRM (Zero-Config Open Default)
No API key is required. Simply run the routing command:

```bash
# Generate road geometries for a single authority
python scripts/routing.py --authority shropshire

# Generate road geometries across all active authorities
python scripts/routing.py --all

# Force regenerate existing route files
python scripts/routing.py --authority somerset --force
```

---

## 3. Output Formats

Outputs are saved directly to `data/routes/`:

- `data/routes/<slug>_routes.geojson`: GeoJSON FeatureCollection containing `LineString` road network coordinates with trip distances and durations.
- `data/routes/<slug>_routes.csv`: Tabular trip segments with Well-Known Text (WKT) geometries:
  - `WKT`, `origin_stop`, `origin_stop_latitude`, `origin_stop_longitude`, `destination_stop`, `destination_stop_latitude`, `destination_stop_longitude`, `distance` (metres), `duration` (seconds), `mobile`, `route`.
