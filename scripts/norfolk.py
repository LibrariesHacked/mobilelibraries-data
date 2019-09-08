import json
from datetime import datetime, timedelta
import re
import csv

## Data extracted using https://maps.norfolk.gov.uk/arcgis/rest/services/layers_ext/where_i_live/MapServer/16/query?f=json&returnGeometry=true&spatialRel=esriSpatialRelIntersects&geometry={"xmin":0.1536,"ymin":52.3553,"xmax":0.9497,"ymax":52.9916,"spatialReference":{"wkid":4326,"latestWkid":4326}}&geometryType=esriGeometryEnvelope&inSR=4326&outFields=*&outSR=4326
DATA_SOURCE_1 = '../raw/norfolk1.json'
# Data extracted using https://maps.norfolk.gov.uk/arcgis/rest/services/layers_ext/where_i_live/MapServer/16/query?f=json&returnGeometry=true&spatialRel=esriSpatialRelIntersects&geometry={"xmin":0.9497,"ymin":52.3553,"xmax":1.7458,"ymax":52.9916,"spatialReference":{"wkid":4326,"latestWkid":4326}}&geometryType=esriGeometryEnvelope&inSR=4326&outFields=*&outSR=4326
DATA_SOURCE_2 = '../raw/norfolk2.json'
DATA_OUTPUT = '../data/norfolk.csv'
DETAILS_RE = '^Mobile Library Route Number (\w+) will next visit (\D+), (.+) on (\d{1,2}\/\d{1,2}\/\d{1,4}) Arrival (\d{1,2}:?[0-5]?\d:[0-5]?\d) Departure (\d{1,2}:?[0-5]?\d:[0-5]?\d)'
TIMETABLE = 'https://www.norfolk.gov.uk/-/media/norfolk/downloads/libraries-and-local-history/mobile-library-timetables/'

def read_data(data_source):

    features = []
    with open(data_source) as data_file:
        data = json.load(data_file)
        for feature in data['features']:
            features.append(feature)

    return features

def run():
    
    four_weeks = timedelta(days=28)
    features = read_data(DATA_SOURCE_1) + read_data(DATA_SOURCE_2)
    features_sorted = sorted(features, key=lambda k: k['attributes']['STOP_NUMBE'])
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

        # Extract stuff from the details
        # e.g. Mobile Library Route Number EDE305 will next visit NORTH ELMHAM, ORCHARD CLOSE No.20 on 18/09/2019 Arrival 16:10 Departure 16:25
        
        # First replace all HH:MM:SS
        
        details_matches = re.compile(DETAILS_RE)
        details_groups = details_matches.search(details)

        community = details_groups.group(2).title()
        date = datetime.strptime(details_groups.group(4), '%d/%m/%Y') - four_weeks
        arrival = details_groups.group(5)[0:5]
        departure = details_groups.group(6)[0:5]

        address = stop_name + ', ' + community
        start = date.strftime('%Y-%m-%d')
        day = date.strftime('%A')

        timetable = TIMETABLE + mobile_library + '-' + route_number + '.pdf'

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
