# Mobile Libaries Data

This is a project for string and transforming data for the [mobile libraries project](https://blog.librarydata.uk/mobile-library-data-project).

## Prerequisites

Primarily scripts will be written in Python (v3).

- [Python](https://www.python.org/)

```
pip install requests
```

## Running scripts

```
ogr2ogr -f "CSV" aberdeenshire_routes.csv aberdeenshire_routes.geojson -lco GEOMETRY=AS_WKT
```

## Authors

* **Dave Rowe** - *Initial work* - [DaveBathnes](https://github.com/DaveBathnes)

See also the list of [contributors](https://github.com/librarieshacked/mobilelibraries-database/contributors) who participated in this project.

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details

## Acknowledgments

* All mobile library services and their data
