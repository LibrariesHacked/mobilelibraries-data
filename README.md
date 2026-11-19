# Mobile Libraries Data

[![Validate mobile library datasets](https://github.com/librarieshacked/mobilelibraries-data/actions/workflows/monitor.yml/badge.svg)](https://github.com/librarieshacked/mobilelibraries-data/actions/workflows/monitor.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Standardised open data, automated harvesters, and road route geometries for UK mobile library stops and timetables across England, Scotland, Wales, and Northern Ireland. Part of the [Libraries Hacked](https://www.librarieshacked.org) project.

For project background and analysis, see the [Mobile Library Data Project](https://blog.librarydata.uk/mobile-library-data-project).

---

## Table of Contents

- [Overview](#overview)
- [Repository Structure](#repository-structure)
- [Data Schema](#data-schema)
- [Recurrence Rule Format (RFC 5545)](#recurrence-rule-format-rfc-5545)
- [Setup & Prerequisites](#setup--prerequisites)
- [Running Harvester Scripts](#running-harvester-scripts)
- [Nationwide Combined Dataset (`scripts/combine.py`)](#nationwide-combined-dataset-scriptscombinepy)
- [Data Validation](#data-validation)
- [Route Geometry Generation](#route-geometry-generation)
- [Authority Services Registry (`services.csv`)](#authority-services-registry-servicescsv)
- [Adding or Updating an Authority](#adding-or-updating-an-authority)
- [License & Acknowledgments](#license--acknowledgments)

---

## Overview

Mobile library services provide vital community outreach across the UK, but timetables are frequently published in fragmented formats (PDF brochures, unstructured HTML tables, Word documents, or image scans).

This repository:
1. **Harvesters & Parsers**: Collects, normalises, and geolocates mobile library timetables across UK library authorities into a uniform, machine-readable format.
2. **Standardised Datasets**: Publishes cleaned, validated CSV datasets conforming to the Frictionless Data Table Schema specification.
3. **Nationwide Compilation**: Automatically aggregates all active authority stops into a single, comprehensive UK dataset available in CSV and GeoJSON.
4. **Frictionless Data Package**: Provides a complete [`datapackage.json`](datapackage.json) descriptor for frictionless ingestion in data pipelines and tools.
5. **Route & Geometry Engine**: Generates realistic road routing between sequential stops using OpenRouteService with an HGV driving profile.
6. **Historical Archive**: Preserves raw timetable snapshots and tracks discontinued stops over time.

---

## Repository Structure

```text
mobilelibraries-data/
├── data/                             # Standardised CSV stops data and routes
│   ├── <slug>.csv                    # Individual authority stops (conforms to schema)
│   ├── uk_mobile_library_stops.csv   # Nationwide combined dataset (8,000+ stops)
│   ├── uk_mobile_library_stops.geojson # Nationwide spatial points (EPSG:4326)
│   ├── library-services.csv          # Local authority code lookup reference
│   └── routes/                       # Generated road routing geometries
│       ├── <slug>_routes.csv         # Road trip segments (WKT Linestring geometries)
│       └── <slug>_routes.geojson     # Road route geometries (GeoJSON)
├── datapackage.json                  # Frictionless Data Package descriptor
├── geocache/                         # Persistent geocoding cache and spatial boundaries
│   ├── authority_bboxes.json         # Spatial bounding boxes for all 48 authorities (safety gates)
│   └── stops_reference.json          # Cached coordinates (Nominatim, OS, postcodes.io)
├── history/                          # Historical datasets
│   └── historical_mobile_stops.csv   # Archived stops from discontinued or updated routes
├── raw/                              # Raw timetable snapshots (HTML, PDF, JSON)
├── schemas/                          # Table Schema specifications
│   ├── mobile-library-stops.json     # Official schema definition for stops datasets
│   └── services-schema.json          # Schema for services.csv registry
├── scripts/                          # Python harvesting, transformation, and utility scripts
│   ├── _common.py                    # Shared helper library (fetching, geocaching, 24h conversion)
│   ├── combine.py                    # Merges all authority stops into unified UK datasets
│   ├── <slug>.py                     # Individual authority scraper/transformer scripts
│   ├── routing.py                    # OpenRouteService road network route generator
│   ├── geocoder.py                   # Standalone geocoding utility
│   ├── ai_extractor.py               # Structured parsing assistant for complex tables
│   └── discover_services.py          # Auditing tool for authority services
├── services.csv                      # Master registry of all 216 UK library authorities
└── requirements.txt                  # Python dependencies
```

---

## Data Schema

The stops data adheres to the [Frictionless Table Schema](https://specs.frictionlessdata.io/table-schema/) defined in [`schemas/mobile-library-stops.json`](schemas/mobile-library-stops.json).

| Field | Type | Format | Description | Example |
| :--- | :--- | :--- | :--- | :--- |
| `Local authority` | string | default | Official name of the library authority | `Conwy County Borough Council` |
| `Local authority code`| string | default | Official ONS/GSS code (`^[ENSW][0-9]{8}$`) | `W06000003` |
| `Mobile name` | string | default | Vehicle identifier or mobile name | `Mobile Library 1` |
| `Route` | string | default | Route or schedule grouping identifier | `Week 1 Tuesday` |
| `Community` | string | default | Town, village, or parish name | `Cerrigydrudion` |
| `Stop` | string | default | Specific stopping place or landmark | `Parish Hall Car Park` |
| `Address` | string | default | Full postal address or location description | `High Street, Cerrigydrudion` |
| `Postcode` | string | default | UK postcode (validated regex format) | `LL21 4ST` |
| `GeoX` | number | default | Longitude in decimal degrees (WGS84, 5 decimal places / ~1.1m precision) | `-3.56120` |
| `GeoY` | number | default | Latitude in decimal degrees (WGS84, 5 decimal places / ~1.1m precision) | `53.02340` |
| `Day` | string | default | Day of week (`Monday` .. `Sunday`) | `Tuesday` |
| `Type` | string | default | Type of stop (`Public`, `Private`, `Dynamic`, `Other`) | `Public` |
| `Arrival` | time | `%H:%M` | Scheduled arrival time in 24-hour clock | `10:15` |
| `Departure` | time | `%H:%M` | Scheduled departure time in 24-hour clock | `11:00` |
| `Frequency` | string | default | iCalendar Recurrence Rule format (RFC 5545 RRULE) | `FREQ=WEEKLY;INTERVAL=3` |
| `Start` | date | `%Y-%m-%d`| Start date of current timetable period | `2026-01-05` |
| `End` | date | `%Y-%m-%d`| End date of timetable period (if defined) | `2026-12-23` |
| `Exceptions` | string | default | Comma-separated bank holidays or closures | `Bank Holidays; Christmas week` |
| `Timetable` | string | uri | Source URL where schedule is published | `https://www.conwy.gov.uk/...` |

---

## Recurrence Rule Format (RFC 5545)

All frequency descriptions in the CSV datasets strictly use the **iCalendar RFC 5545 RRULE** specification as required by the schema:

- **Weekly / Multi-week intervals**:
  - `FREQ=WEEKLY;INTERVAL=1` (Every week)
  - `FREQ=WEEKLY;INTERVAL=2` (Every 2 weeks / fortnightly)
  - `FREQ=WEEKLY;INTERVAL=3` (Every 3 weeks)
  - `FREQ=WEEKLY;INTERVAL=4` (Every 4 weeks)
- **Monthly by weekday pattern**:
  - `FREQ=MONTHLY;BYDAY=1MO` (First Monday of every month)
  - `FREQ=MONTHLY;BYDAY=3TH` (Third Thursday of every month)
  - `FREQ=MONTHLY;BYDAY=2WE,4WE` (Second and fourth Wednesday of every month)

---

## Spatial Validation & Bounding Box Gating

To prevent common geocoding errors (such as homonym village names resolving to distant counties or other nations):
- All geocoders enforce geographic bounding box gating defined in [`geocache/authority_bboxes.json`](geocache/authority_bboxes.json).
- Candidate coordinates outside an authority's spatial envelope are automatically rejected.
- When an accurate local position cannot be determined within the boundary, stop coordinates remain blank (`""`) rather than placing the stop in a bogus location.
- Exact curb locations can be permanently pinned in [`geocache/stops_reference.json`](geocache/stops_reference.json).

---

## Setup & Prerequisites

Python 3.10+ is recommended.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/librarieshacked/mobilelibraries-data.git
   cd mobilelibraries-data
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## Running Harvester Scripts

Each authority has an independent Python script in the `scripts/` directory.

Run any script directly from the repository root:

```bash
python scripts/conwy.py
```

Scrapers use [`scripts/_common.py`](scripts/_common.py) to:
- Cache raw downloaded files to `raw/<slug>/`
- Normalize arrival/departure times into 24-hour `%H:%M` strings
- Cache geocoded locations in `geocache/stops_reference.json`
- Output clean CSVs to `data/<slug>.csv`
- Validate outputs against the schema automatically

---

## Nationwide Combined Dataset (`scripts/combine.py`)

To aggregate all active authority datasets into a single nationwide view:

```bash
python scripts/combine.py
```

This generates:
- **`data/uk_mobile_library_stops.csv`**: Unified CSV containing over 8,100 stops with identical 19-column schema.
- **`data/uk_mobile_library_stops.geojson`**: Spatial Point features for every stop with valid coordinates (over 7,600 stops), ready for web maps, GIS (QGIS, ArcGIS), Kepler.gl, or MapLibre.
- **`data/library-services.csv`**: Authority code lookup to satisfy foreign key relations.

---

## Data Validation

### 1. Validate the Entire Data Package
The entire collection of datasets can be validated using the [Frictionless](https://framework.frictionlessdata.io/) Data Package descriptor:

```bash
frictionless validate datapackage.json
```

### 2. Validate an Individual Dataset
```bash
frictionless validate data/conwy.csv --schema schemas/mobile-library-stops.json
```

### 3. Automated CI/CD
A GitHub Actions workflow ([`.github/workflows/monitor.yml`](.github/workflows/monitor.yml)) runs on push and schedule to validate all datasets against the schema and ensure the aggregated nationwide datasets build cleanly.

---

## Route Geometry Generation

The unified routing tool ([`scripts/routing.py`](scripts/routing.py)) generates road geometries between consecutive stops on a given route using the [OpenRouteService API](https://openrouteservice.org/) (with the `driving-hgv` profile suitable for heavy mobile library vehicles).

1. Obtain a free OpenRouteService API key.
2. Set the environment variable:
   - **Linux / macOS:** `export ORS_API_KEY="your-key-here"`
   - **Windows (PowerShell):** `$env:ORS_API_KEY="your-key-here"`
3. Run the routing tool for an authority or all:
   ```bash
   # Single authority
   python scripts/routing.py --authority conwy

   # All authorities
   python scripts/routing.py --all
   ```
   Outputs are saved to `data/routes/`:
   - `data/routes/<slug>_routes.geojson`: LineString features connecting sequential stops with drive durations and distances.
   - `data/routes/<slug>_routes.csv`: Well-Known Text (WKT) table with route segments.

---

## Authority Services Registry (`services.csv`)

[`services.csv`](services.csv) is the master register tracking mobile library provision across all **216 UK library authorities**.

Key fields:
- `local_authority`: Common local authority name.
- `official_name`: Full legal/administrative name.
- `local_authority_code`: Official ONS/GSS administrative code (e.g. `E10000031`, `W06000003`).
- `nation`: UK nation (`England`, `Scotland`, `Wales`, `Northern Ireland`).
- `authority_type`: Local government type (e.g., `County Council`, `Unitary Authority`, `Metropolitan District`).
- `dataset_slug`: Unique slug matching the filename in `data/` and `scripts/` (e.g., `conwy`, `warwickshire`).
- `has_mobile_service`: `Yes` or `No`.
- `status`: Provision status:
  - `Active Verified` (50): Service confirmed operating with published stops timetable.
  - `No Mobile (Urban/Home Delivery)` (123): Authority has no mobile library service (urban councils or home library service only).
  - `Discontinued` (34): Service historically operated but has since been terminated.
  - `Active (No Public Timetable)` (2): Active service operates (e.g. Isle of Anglesey, Ceredigion), but stops are on-demand, school-based, or arranged privately.
  - `Active - On Demand` (1): On-demand mobile service (Comhairle nan Eilean Siar / Western Isles).
  - `Dissolved Historic Council` (4): Historic authorities abolished under local government reorganisation.
- `source_url`: Official public timetable page or consultation page.
- `last_checked` / `last_updated`: Date of verification and last data update.
- `notes`: Key contextual details (vehicle fleet notes, route rotation cycles, or discontinuation evidence).

---

## Adding or Updating an Authority

When adding or updating an authority parser:

1. **Use `_common.py`**:
   Leverage the standardized helpers in `scripts/_common.py`:
   - `http_get()` for rate-limited, user-agent compliant web requests.
   - `save_raw()` for saving raw timetable documents to `raw/<slug>/`.
   - `to_24h()` for parsing mixed time formats (`10.30am`, `14:00`, `9:45`).
   - `load_geocache()` / `save_geocache()` / `geocode_place()` for consistent geocoding.
   - `validate_dataset()` to ensure outputs pass schema checks before completing.
2. **Follow Schema Standards**:
   Ensure all 19 schema columns are present, postcodes are uppercase and formatted with a space (e.g. `LL21 4ST`), arrival/departure times are 24-hour `%H:%M`, and `Frequency` uses RFC 5545 RRULE format (`FREQ=WEEKLY;INTERVAL=2`).
3. **Archive Discontinued Stops**:
   If an authority withdraws stops, call `_common.archive_stops()` to append discontinued stops to `history/historical_mobile_stops.csv`.
4. **Update `services.csv` and Combine**:
   Update `services.csv` and run `python scripts/combine.py` to refresh the nationwide dataset.

---

## License & Acknowledgments

- **Code**: Licensed under the [MIT License](LICENSE.md).
- **Data**: Data is extracted and transformed from public authority publications under the [Open Government Licence v3.0](http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) where applicable.
- **Acknowledgments**: Thank you to all UK local authority library services, library staff, and the open data community.
