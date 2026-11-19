# Mobile Libraries Data

[![Validate mobile library datasets](https://github.com/librarieshacked/mobilelibraries-data/actions/workflows/monitor.yml/badge.svg)](https://github.com/librarieshacked/mobilelibraries-data/actions/workflows/monitor.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Standardised open data, automated harvesters, and road route geometries for UK mobile library stops and timetables across England, Scotland, Wales, and Northern Ireland. Part of the [Libraries Hacked](https://www.librarieshacked.org) project.

For project background and analysis, see the [Mobile Library Data Project](https://blog.librarydata.uk/mobile-library-data-project).

---

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for data analysis, application development, and running harvesting pipelines.

### Prerequisites

You need Python 3.10 or later installed on your system.

```bash
python --version
```

### Installing

1. **Clone the repository:**
   ```bash
   git clone https://github.com/librarieshacked/mobilelibraries-data.git
   cd mobilelibraries-data
   ```

2. **Create and activate a virtual environment (optional but recommended):**
   ```bash
   python -m venv .venv
   # Windows (PowerShell):
   .venv\Scripts\Activate.ps1
   # Linux / macOS:
   source .venv/bin/activate
   ```

3. **Install required dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## Usage

### Running an Authority Scraper

Each authority has an independent Python script in the `scripts/` directory that fetches timetables, normalises coordinates, and outputs to `data/<slug>.csv`:

```bash
python scripts/conwy.py
```

### Building the Nationwide Dataset

To aggregate all individual local authority datasets into a single UK-wide view:

```bash
python scripts/combine.py
```

This generates:
* **`data/uk_mobile_library_stops.csv`**: Unified CSV containing over 8,100 stops with identical 19-column schema.
* **`data/uk_mobile_library_stops.geojson`**: Spatial Point features (WGS84, 5 decimal places) ready for web maps, GIS (QGIS, ArcGIS), Kepler.gl, or MapLibre.
* **`data/library-services.csv`**: Local authority code lookup to satisfy foreign key relations.

### Generating Road Routing Geometries

To generate realistic road geometries between sequential stops using OpenRouteService with an HGV driving profile:

```bash
# Requires ORS_API_KEY environment variable
python scripts/routing.py --authority conwy
```

Outputs are saved to `data/routes/<slug>_routes.geojson` and `data/routes/<slug>_routes.csv`. See [docs/routing.md](docs/routing.md) for full instructions.

---

## Data & Documentation

Detailed documentation has been separated into dedicated reference guides:

* **[Data Schema & Recurrence Rules](docs/schema.md)**: Complete 19-column data dictionary, field constraints, and RFC 5545 RRULE format examples.
* **[Geocoding & Spatial Standards](docs/geocoding.md)**: Coordinate precision standards (5 decimal places / ~1.1m resolution) and bounding box safety envelopes.
* **[Route Geometry Generation](docs/routing.md)**: OpenRouteService road routing pipeline and output specifications.
* **[Authority Services Registry](docs/services-registry.md)**: Complete documentation of `services.csv` tracking all 216 UK library authorities.
* **[Contributing Guide](docs/contributing.md)**: Instructions for developing new scrapers and submitting pull requests.

---

## Running the Tests & Data Validation

The repository includes a Frictionless Data Package descriptor ([`datapackage.json`](datapackage.json)) and automated schema validation.

### Validate the Entire Data Package

```bash
frictionless validate datapackage.json
```

### Validate an Individual Authority Dataset

```bash
frictionless validate data/conwy.csv --schema schemas/mobile-library-stops.json
```

Automated validation runs on every commit and on a weekly schedule via GitHub Actions ([`.github/workflows/monitor.yml`](.github/workflows/monitor.yml)).

---

## Built With

* [Python 3](https://www.python.org/) - Primary language for harvesting and data transformation
* [Frictionless Data](https://framework.frictionlessdata.io/) - Data package descriptor and schema validation
* [Postcodes.io](https://postcodes.io/) - Free, open-source UK postcode and place lookup API
* [OpenStreetMap Nominatim](https://nominatim.openstreetmap.org/) - Geocoding fallback
* [OpenRouteService](https://openrouteservice.org/) - Road network routing and isochrones
* [pdfplumber](https://github.com/jsvine/pdfplumber) - Table and coordinate extraction from timetable PDFs
* [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) - HTML parsing

---

## Contributing

Please read [docs/contributing.md](docs/contributing.md) for details on our code of conduct, and the process for submitting pull requests to us.

---

## Versioning

We use [SemVer](http://semver.org/) for dataset versioning via the Frictionless Data Package descriptor ([`datapackage.json`](datapackage.json)).

---

## Authors

* **Libraries Hacked** - *Initial work & maintenance* - [Libraries Hacked](https://www.librarieshacked.org)

See also the list of [contributors](https://github.com/librarieshacked/mobilelibraries-data/contributors) who participated in this project.

---

## License

* **Code:** Licensed under the [MIT License](LICENSE.md).
* **Data:** Sourced and transformed from public authority publications under the [Open Government Licence v3.0](http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) where applicable.

---

## Acknowledgments

* UK local authority library services and dedicated mobile library teams
* OpenStreetMap contributors
* Ordnance Survey OpenData
