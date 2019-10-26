import json
from datetime import datetime, timedelta
import re
import csv

# Data extracted using https://gis1.westberks.gov.uk/arcgis/rest/services/maps/Wbc_Leisure/MapServer/1/query?f=json&returnGeometry=true&spatialRel=esriSpatialRelIntersects&geometry={%22xmin%22:-1.5881,%22ymin%22:51.329,%22xmax%22:51.5637,%22ymax%22:51.5637,%22spatialReference%22:{%22wkid%22:4326,%22latestWkid%22:4326}}&geometryType=esriGeometryEnvelope&inSR=4326&outFields=*&outSR=4326
DATA_SOURCE = '../raw/west_berkshire.json'
DATA_OUTPUT = '../data/west_berkshire.csv'
TIMETABLE = 'http://info.westberks.gov.uk/mobilelibraries'

def read_data(data_source):

    features = []
    with open(data_source) as data_file:
        data = json.load(data_file)
        for feature in data['features']:
            features.append(feature)

    return features

def run():

    features = read_data(DATA_SOURCE)
    features_sorted = sorted(features, key=lambda k: (k['attributes']['ROUTE']))

    mobiles = []
    mobile_name = 'Mobile'
    organisation = 'West Berkshire'
    frequency = 'FREQ=WEEKLY;INTERVAL=3'

    for feature in features_sorted:

        route = feature['attributes']['ROUTE'][0:1]
        times = feature['attributes']['TIME']
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

        dates_search = re.search(r'Oct: (\d{1,2})', dates)
        date = datetime.strptime(dates_search.group(1) + ' Oct 2019', '%d %b %Y')
        start = date.strftime('%Y-%m-%d')
        day = date.strftime('%A')

        mobiles.append(
            [mobile_name, route, community, stop_name, address, '', longitude, latitude,
                day, arrival, departure, frequency, start, '', TIMETABLE]
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
