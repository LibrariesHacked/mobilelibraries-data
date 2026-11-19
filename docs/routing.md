# Route Geometry Generation

This repository includes a routing engine in [`scripts/routing.py`](../scripts/routing.py) that generates realistic road geometries and travel estimates between consecutive stops on mobile library routes.

---

## 1. Routing Profile & Technology

Mobile libraries are large, heavy commercial vehicles that cannot travel down pedestrian alleys, restricted lanes, or narrow bridges. 

- **Routing Provider:** [OpenRouteService (ORS)](https://openrouteservice.org/)
- **Driving Profile:** `driving-hgv` (Heavy Goods Vehicle)
- **Geometry Format:** Full road network linestrings following realistic driving paths, not straight-line (crow-flies) vectors.

---

## 2. Setting Up OpenRouteService

To generate route geometries, you need an OpenRouteService API key (free tier available):

1. Register at [openrouteservice.org/sign-up](https://openrouteservice.org/sign-up).
2. Export your token in your environment:
   - **Linux / macOS:**
     ```bash
     export ORS_API_KEY="your-api-key"
     ```
   - **Windows (PowerShell):**
     ```powershell
     $env:ORS_API_KEY="your-api-key"
     ```

---

## 3. Generating Routes

Run [`scripts/routing.py`](../scripts/routing.py) directly from the repository root:

```bash
# Generate road geometries for a single authority
python scripts/routing.py --authority conwy

# Generate road geometries across all active authorities
python scripts/routing.py --all
```

---

## 4. Output Formats

Outputs are saved directly to `data/routes/`:

### 1. `data/routes/<slug>_routes.geojson`
A GeoJSON `FeatureCollection` containing:
- **Geometry:** `LineString` coordinate sequences following the road network.
- **Properties:**
  - `route`: Route identifier.
  - `from_stop`: Departure stop name.
  - `to_stop`: Destination stop name.
  - `distance_km`: Driving distance in kilometres.
  - `duration_mins`: Driving duration in minutes.

### 2. `data/routes/<slug>_routes.csv`
A tabular representation with Well-Known Text (WKT) linestring geometries:
- `Route`, `Day`, `From_Stop`, `To_Stop`, `Distance_km`, `Duration_mins`, `WKT_Geometry`.
