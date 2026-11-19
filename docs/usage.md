# Usage & Workflows

This guide covers running harvesters, aggregating nationwide datasets, and generating road route geometries.

---

## 1. Running an Authority Harvester

Each authority has an independent scraper script in the `scripts/` directory that fetches live timetables, normalises coordinates, and outputs to `data/<slug>.csv`:

```bash
# Run a specific authority scraper
python scripts/conwy.py
python scripts/leicestershire.py
python scripts/highland.py
```

Harvester scripts:
* Fetch source timetable documents (HTML, PDF, ArcGIS REST endpoints).
* Store raw responses in `raw/<slug>/<date>/`.
* Format dates and times into standard 24-hour `%H:%M` format.
* Normalise coordinates to 5 decimal places (~1.1 m precision).
* Validate output against `schemas/mobile-library-stops.json`.

---

## 2. Aggregating the Nationwide Dataset

To combine all 48 local authority datasets into a single nationwide view:

```bash
python scripts/combine.py
```

This generates:
* **`data/uk_mobile_library_stops.csv`**: Unified CSV containing over 8,100 stops with the 19-column Table Schema.
* **`data/uk_mobile_library_stops.geojson`**: Spatial Point features (WGS84, 5 decimal places) ready for web maps, GIS (QGIS, ArcGIS), Kepler.gl, or MapLibre.
* **`data/library-services.csv`**: Reference lookup of statutory local authority codes (`Local authority code` -> `Local authority`) satisfying foreign keys in the Data Package.

---

## 3. Generating Road Route Geometries

To compute realistic driving routes between sequential stops on each mobile route schedule:

```bash
# Generate routes for a single authority
python scripts/routing.py --authority shropshire

# Generate routes across all authorities
python scripts/routing.py --all

# Force regeneration of existing route files
python scripts/routing.py --authority somerset --force
```

### Routing Engines
* **OSRM (Default):** Runs against the OpenStreetMap road network with zero setup or API keys needed.
* **OpenRouteService (`driving-hgv`):** Enabled when `ORS_API_KEY` is set in the environment for Heavy Goods Vehicle restrictions.

Outputs are written to:
* `data/routes/<slug>_routes.geojson`: GeoJSON LineString geometries following public roads.
* `data/routes/<slug>_routes.csv`: Tabular road trip segments with Well-Known Text (WKT) geometries, driving distances (metres), and durations (seconds).

See [docs/routing.md](routing.md) for complete details.
