"""West Berkshire: convert the council ArcGIS MapServer extract (raw/west_berkshire.json)
into data/west_berkshire.csv.

The query used to extract the JSON is noted above DATA_SOURCE. The service closed in
March 2025 - see history/ for the archived stops.
"""

import json
from datetime import datetime, timedelta
import re
import csv
from _common import create_mobile_library_file

# Data extracted using https://gis1.westberks.gov.uk/arcgis/rest/services/maps/Wbc_Leisure/MapServer/1/query?f=json&returnGeometry=true&spatialRel=esriSpatialRelIntersects&geometry={%22xmin%22:-1.5881,%22ymin%22:51.329,%22xmax%22:51.5637,%22ymax%22:51.5637,%22spatialReference%22:{%22wkid%22:4326,%22latestWkid%22:4326}}&geometryType=esriGeometryEnvelope&inSR=4326&outFields=*&outSR=4326
DATA_SOURCE = '../raw/west_berkshire.json'
DATA_OUTPUT = '../data/west_berkshire.csv'
TIMETABLE = 'http://info.westberks.gov.uk/mobilelibraries'

def read_data(data_source):
    """Load the ArcGIS JSON file at data_source and return its list of feature dicts."""

    features = []
    with open(data_source) as data_file:
        data = json.load(data_file)
        for feature in data['features']:
            features.append(feature)

    return features

def run():
    """Parse archived West Berkshire stop features and write data/west_berkshire.csv."""

    features = read_data(DATA_SOURCE)
    features_sorted = sorted(features, key=lambda k: (k['attributes']['ROUTE']))

    mobiles = []
    mobile_name = 'Mobile'
    organisation = 'West Berkshire'
    frequency = 'FREQ=WEEKLY;INTERVAL=3'

    for feature in features_sorted:

        # Route identifier is the leading character of the ROUTE field
        route = feature['attributes']['ROUTE'][0:1]
        times = feature['attributes']['TIME']
        # Extract arrival and departure HH.MM pairs from the free-text TIME string
        times_result = re.search(r'(\d{2}.\d{2}).*(\d{2}.\d{2})', times)
        arrival = times_result.group(1).replace('.', ':')
        departure = times_result.group(2).replace('.', ':')
        day = feature['attributes']['DAY']
        community = feature['attributes']['VILLAGE']
        stop_name = feature['attributes']['STOP']
        address = feature['attributes']['NAME']
        dates = feature['attributes']['DATES']

        longitude = feature['geometry']['x']
        latitude = feature['geometry']['y']

        # Anchor start date and weekday to the first October 2019 visit date in DATES
        dates_search = re.search(r'Oct: (\d{1,2})', dates)
        date = datetime.strptime(dates_search.group(1) + ' Oct 2019', '%d %b %Y')
        start = date.strftime('%Y-%m-%d')
        day = date.strftime('%A')

        mobiles.append(
            [mobile_name, route, community, stop_name, address, '', longitude, latitude,
                day, 'Public', arrival, departure, frequency, start, '', '', TIMETABLE]
        )

    create_mobile_library_file(organisation, 'west_berkshire.csv', mobiles)

run()
