# Mobile libaries data

This repository is for transforming data for the [mobile libraries project](https://blog.librarydata.uk/mobile-library-data-project).

## Prerequisites

Scripts will be written in Python v3.

- [Python](https://www.python.org/)

```
pip install geopandas
pip install beautifulsoup4
pip install requests
```

Geopandas will need rtree, pyproj, fiona, gdal (v2), and shapely to be installed. For Windows systems these are all available at:

[Python Libraries](https://www.lfd.uci.edu/~gohlke/pythonlibs/)

## Running scripts

Each individual scrpt can be run from the command line. For example:

```python
python3 north_somerset.py
```

Run the following when in the data directory for each authority.

```
ogr2ogr -f "CSV" aberdeenshire_routes.csv aberdeenshire_routes.geojson -lco GEOMETRY=AS_WKT
```

## Authors

- **Dave Rowe** - _Initial work_ - [DaveBathnes](https://github.com/DaveBathnes)

See also the list of [contributors](https://github.com/librarieshacked/mobilelibraries-database/contributors) who participated in this project.

## License

All code in this project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

## Acknowledgments

- All mobile library services and their data
