"""Leeds: convert the three ArcGIS amenity layers (children, older people, community)
saved in raw/ (ArcGIS JSON) into one stops CSV (target: data/leeds.csv; script currently retains unfinished template values).

The ArcGIS query URL for each layer is noted above its DATA_SOURCE constant.
"""

import json
from datetime import datetime, timedelta
import re
import csv
from _common import create_mobile_library_file

# https://gis2.leeds.gov.uk/arcgis/rest/services/Public/Amenities/FeatureServer/3/query?f=json&returnGeometry=true&spatialRel=esriSpatialRelIntersects&geometry={"xmin":-2.0114,"ymin":53.6252,"xmax":-0.9429,"ymax":54.0337,"spatialReference":{"wkid":4326,"latestWkid":4326}}&geometryType=esriGeometryEnvelope&inSR=4326&outFields=*&outSR=4326
DATA_SOURCE_1 = '../raw/leeds_children.json'
# https://gis2.leeds.gov.uk/arcgis/rest/services/Public/Amenities/FeatureServer/5/query?f=json&returnGeometry=true&spatialRel=esriSpatialRelIntersects&geometry={"xmin":-2.0114,"ymin":53.6252,"xmax":-0.9429,"ymax":54.0337,"spatialReference":{"wkid":4326,"latestWkid":4326}}&geometryType=esriGeometryEnvelope&inSR=4326&outFields=*&outSR=4326
DATA_SOURCE_2 = '../raw/leeds_older.json'
# https://gis2.leeds.gov.uk/arcgis/rest/services/Public/Amenities/FeatureServer/4/query?f=json&returnGeometry=true&spatialRel=esriSpatialRelIntersects&geometry={"xmin":-2.0114,"ymin":53.6252,"xmax":-0.9429,"ymax":54.0337,"spatialReference":{"wkid":4326,"latestWkid":4326}}&geometryType=esriGeometryEnvelope&inSR=4326&outFields=*&outSR=4326
# Note: overwrites DATA_SOURCE_2 above; third layer is not yet merged separately
DATA_SOURCE_2 = '../raw/leeds_community.json'

TIMETABLE = ''


def read_data(data_source):
    """Load an ArcGIS JSON file from data_source and return its list of feature dicts."""

    features = []
    with open(data_source) as data_file:
        data = json.load(data_file)
        for feature in data['features']:
            features.append(feature)

    return features


def run():
    """Load, sort, and deduplicate ArcGIS stop features, extract timetable fields, and write the output CSV."""

    features = read_data(DATA_SOURCE_1) + read_data(DATA_SOURCE_2)
    features_sorted = sorted(features, key=lambda k: k['attributes']['STOP_NUMBE'])
    # Keep only the last occurrence of any identical feature dict in the sorted list
    features_deduped = [i for n, i in enumerate(features_sorted) if i not in features_sorted[n + 1:]]

    mobiles = []
    organisation = 'Norfolk'
    frequency = 'FREQ=WEEKLY;INTERVAL=4'

    for feature in features_deduped:

        route = feature['attributes']['ROUTE_NUMB']
        stop_name = feature['attributes']['STOP_NAME'].title()
        details = feature['attributes']['DETAILS']

        longitude = feature['geometry']['x']
        latitude = feature['geometry']['y']

        # Make the mobile library the first 3 letters of the route
        mobile_library = route[0:3]
        route_number = route[3:6]

        if mobile_library == 'CEN':
            mobile_library = 'CEN' + CEN_Routes[route]

        # Extract stuff from the details
        # e.g. Mobile Library Route Number EDE305 will next visit NORTH ELMHAM, ORCHARD CLOSE No.20 on 18/09/2019 Arrival 16:10 Departure 16:25

        # First replace all HH:MM:SS

        details_matches = re.compile(DETAILS_RE)
        details_groups = details_matches.search(details)

        community = details_groups.group(2).title()
        date = datetime.strptime(
            details_groups.group(4), '%d/%m/%Y') - four_weeks
        arrival = details_groups.group(5)[0:5]
        departure = details_groups.group(6)[0:5]

        address = stop_name + ', ' + community
        start = date.strftime('%Y-%m-%d')
        day = date.strftime('%A')

        timetable = TIMETABLE + mobile_library + '-' + route_number + '.pdf'

        mobiles.append(
            [mobile_library, route, community, stop_name, address, '', longitude, latitude,
                day, 'Public', arrival, departure, frequency, start, '', '', timetable]
        )

    create_mobile_library_file(organisation, 'norfolk.csv', mobiles)


run()
