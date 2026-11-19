# Mobile Libraries Data

[![Validate mobile library datasets](https://github.com/librarieshacked/mobilelibraries-data/actions/workflows/monitor.yml/badge.svg)](https://github.com/librarieshacked/mobilelibraries-data/actions/workflows/monitor.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Standardised open data, automated harvesters, and road route geometries for UK mobile library stops and timetables across England, Scotland, Wales, and Northern Ireland. Part of the [Libraries Hacked](https://www.librarieshacked.org) project.

For background and analysis, see the [Mobile Library Data Project](https://blog.librarydata.uk/mobile-library-data-project).

---

## Getting Started

### Prerequisites

* Python 3.10 or later

### Installation

```bash
git clone https://github.com/librarieshacked/mobilelibraries-data.git
cd mobilelibraries-data
pip install -r requirements.txt
```

### Quick Commands

* **Validate data:** `python scripts/validate.py`
* **Combine UK dataset:** `python scripts/combine.py`
* **Generate routes:** `python scripts/routing.py --all`
* **Run authority scraper:** `python scripts/<slug>.py`

For full workflow options, see [Usage & Workflows](docs/usage.md).

---

## Documentation

Detailed documentation is organised into dedicated guides:

* **[Data Schema & Recurrence Rules](docs/schema.md)** - 19-column data dictionary, field constraints, and RFC 5545 RRULE format.
* **[Geocoding & Spatial Standards](docs/geocoding.md)** - 5-decimal place precision and authority bounding boxes.
* **[Route Geometry Generation](docs/routing.md)** - Road network routing via OSRM and OpenRouteService.
* **[Authority Services Registry](docs/services-registry.md)** - Master status register (`services.csv`) for all 216 UK library authorities.
* **[Usage & Workflows](docs/usage.md)** - Running scrapers, combining datasets, and routing instructions.
* **[Data Validation & Testing](docs/validation.md)** - Frictionless Data Package and automated quality checks.
* **[Contributing Guide](docs/contributing.md)** - Steps for adding new authority scrapers and submitting PRs.

---

## Built With

* [Python 3](https://www.python.org/) - Scraping and ETL pipelines
* [Frictionless Data](https://framework.frictionlessdata.io/) - Data Package standards and validation
* [Postcodes.io](https://postcodes.io/) - UK postcode geocoding API
* [OpenStreetMap](https://www.openstreetmap.org/) & [OSRM](http://project-osrm.org/) - Open road network and routing
* [OpenRouteService](https://openrouteservice.org/) - HGV commercial vehicle routing

---

## Versioning

We use [SemVer](http://semver.org/) for dataset versioning via [`datapackage.json`](datapackage.json).

---

## Authors

* **Libraries Hacked** - [Libraries Hacked](https://www.librarieshacked.org)

See the list of [contributors](https://github.com/librarieshacked/mobilelibraries-data/contributors) who participated in this project.

---

## License

* **Code:** Licensed under the [MIT License](LICENSE.md).
* **Data:** Sourced and transformed from public authority publications under the [Open Government Licence v3.0](http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) where applicable.

---

## Acknowledgments

* UK local authority library services and dedicated mobile library teams
* [OpenStreetMap](https://www.openstreetmap.org/) contributors
* [Ordnance Survey](https://www.ordnancesurvey.co.uk/) OpenData
