import json
from datetime import datetime, timedelta
import re
import csv
from _common import create_mobile_library_file

## Data extracted using https://maps.shropshire.gov.uk/arcgis/rest/services/AGOL/AGOL_embMapLayers/MapServer/6/query?f=json&returnGeometry=true&spatialRel=esriSpatialRelIntersects&geometry={"xmin":-3.2355,"ymin":52.3063,"xmax":-2.2329,"ymax":52.9984,"spatialReference":{"wkid":4326,"latestWkid":4326}}&geometryType=esriGeometryEnvelope&inSR=4326&outFields=*&outSR=4326
DATA_SOURCE = '../raw/shropshire.json'
TIMETABLE = 'https://www.shropshire.gov.uk/libraries/mobile-libraries/'


def read_data(data_source):

    features = []
    with open(data_source) as data_file:
        data = json.load(data_file)
        for feature in data['features']:
            features.append(feature)

    return features


def run():

    features = read_data(DATA_SOURCE)
    features_sorted = sorted(features, key=lambda k: (
        k['attributes']['Route'], k['attributes']['Stop']))

    mobiles = []
    frequency = 'FREQ=WEEKLY;INTERVAL=2'

    for feature in features_sorted:

        route = feature['attributes']['Route']
        place = feature['attributes']['Place']
        stop_name = place.split(';')[-1].strip().title().replace("'S", "'s")
        community = place.split(';')[0].strip().title().replace("'S", "'s")
        address = stop_name + ', ' + community
        date = datetime.utcfromtimestamp(
            int(feature['attributes']['Date1']) / 1000)
        start = date.strftime('%Y-%m-%d')
        day = date.strftime('%A')
        arrival = feature['attributes']['From_']
        departure = feature['attributes']['To']
        mobile_name = feature['attributes']['Fullname'].replace(
            ' Mobile Library', '')

        longitude = feature['geometry']['x']
        latitude = feature['geometry']['y']

        mobiles.append(
            [mobile_name, route, community, stop_name, address, '', longitude, latitude,
                day, 'Public', arrival, departure, frequency, start, '', '', TIMETABLE]
        )

    create_mobile_library_file('Shropshire', 'shropshire.csv', mobiles)


run()
