# Mobile libraries data

[![Validate mobile library datasets](https://github.com/librarieshacked/mobilelibraries-data/actions/workflows/monitor.yml/badge.svg)](https://github.com/librarieshacked/mobilelibraries-data/actions/workflows/monitor.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This project collects and publishes open data about UK mobile library services. It brings together timetables, stop locations, and driving routes across England, Scotland, Wales, and Northern Ireland into clean, consistent files.

It is part of the [Libraries Hacked](https://www.librarieshacked.org) project. For background and analysis, see the [Mobile Library Data Project](https://blog.librarydata.uk/mobile-library-data-project).

## Getting started

### What you need

* Python 3.10 or later installed on your computer.

### How to install

```bash
git clone https://github.com/librarieshacked/mobilelibraries-data.git
cd mobilelibraries-data
pip install -r requirements.txt
```

### Quick commands

* **Check the data:** `python scripts/validate.py`
* **Combine all UK stops:** `python scripts/combine.py`
* **Work out driving routes:** `python scripts/routing.py --all`
* **Update a single council:** `python scripts/<council_name>.py`

For more details, see [how to run the scripts](docs/usage.md).

## Documentation

More information is available in these guides:

* **[Data schema and visit frequency](docs/schema.md)** - What each column in the files means and how visit cycles are written.
* **[Location and map coordinates](docs/geocoding.md)** - How stop locations are found, checked, and kept accurate.
* **[Driving routes between stops](docs/routing.md)** - How road routes and travel times are worked out.
* **[List of all UK library services](docs/services-registry.md)** - The master list of all 216 UK library authorities and their mobile status.
* **[How to run the scripts](docs/usage.md)** - How to update council data, combine stops, and run the route tools.
* **[Data checking and quality](docs/validation.md)** - How we test that files are complete and correctly formatted.
* **[How to contribute](docs/contributing.md)** - How to help by adding a council or updating a timetable.

## Built with

* [Python 3](https://www.python.org/) - Code for collecting and cleaning data
* [Frictionless Data](https://framework.frictionlessdata.io/) - Data standards and automated checking
* [Postcodes.io](https://postcodes.io/) - Free UK postcode location service
* [OpenStreetMap](https://www.openstreetmap.org/) and [OSRM](http://project-osrm.org/) - Map data and road routing
* [OpenRouteService](https://openrouteservice.org/) - Lorry-friendly road routing

## Versioning

We use [SemVer](http://semver.org/) version numbers in [`datapackage.json`](datapackage.json).

## Authors

* **Libraries Hacked** - [Libraries Hacked](https://www.librarieshacked.org)

See the list of [contributors](https://github.com/librarieshacked/mobilelibraries-data/contributors) who have helped with this project.

## License

* **Code:** Licensed under the [MIT License](LICENSE.md).
* **Data:** Sourced and adapted from council publications under the [Open Government Licence v3.0](http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) where applicable.

## Acknowledgments

* Council library services and dedicated mobile library drivers and staff
* [OpenStreetMap](https://www.openstreetmap.org/) contributors
* [Ordnance Survey](https://www.ordnancesurvey.co.uk/) OpenData
