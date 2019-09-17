import json
from datetime import datetime, timedelta
import re
import csv

## Data extracted using https://maps.york.gov.uk/arcgis/rest/services/Public/LV_LeisureCulture/MapServer/8/query?f=json&returnGeometry=true&spatialRel=esriSpatialRelIntersects&geometry={"xmin":-1.345436,"ymin":53.836224,"xmax":-0.802066,"ymax":54.092055,"spatialReference":{"wkid":4326,"latestWkid":4326}}&geometryType=esriGeometryEnvelope&inSR=4326&outFields=*&outSR=4326
DATA_SOURCE = '../raw/york.json'
DATA_OUTPUT = '../data/york.csv'

TIMETABLE = 'https://www.exploreyork.org.uk/mobile-library/'

def read_data(data_source):

    features = []
    with open(data_source) as data_file:
        data = json.load(data_file)
        for feature in data['features']:
            features.append(feature)

    return features

def run():
    
    features = read_data(DATA_SOURCE)
    features_sorted = sorted(features, key=lambda k: k['attributes']['ADDRESS'])

    mobiles = []
    organisation = 'York'
    frequency = 'FREQ=WEEKLY;INTERVAL=2'

    for feature in features_sorted:

        route = ''
        stop_name = feature['attributes']['ADDRESS']

        longitude = feature['geometry']['x']
        latitude = feature['geometry']['y']

        # Make the mobile library the first 3 letters of the route
        mobile_library = 'Mobile'

        community = feature['attributes']['ADDRESS']
        date = ''
        arrival = ''
        departure = ''

        address = feature['attributes']['ADDRESS']
        start = ''
        day = ''

        timetable = TIMETABLE

        mobiles.append(
            [mobile_library, route, community, stop_name, address, '', longitude, latitude,
                day, arrival, departure, frequency, start, '', timetable]
        )

    with open(DATA_OUTPUT, 'w', encoding='utf8', newline='') as out_csv:
        mob_writer = csv.writer(out_csv, delimiter=',',
                                quotechar='"', quoting=csv.QUOTE_MINIMAL)
        mob_writer.writerow(
            ['organisation', 'mobile', 'route', 'community', 'stop', 'address', 'postcode', 'geox',
             'geoy', 'day', 'arrival', 'departure', 'frequency', 'start', 'end',  'timetable'])
        for sto in mobiles:
            mob_writer.writerow(
                [organisation, sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])

run()
