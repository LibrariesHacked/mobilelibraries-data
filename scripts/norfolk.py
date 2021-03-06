import json
from datetime import datetime, timedelta
import re
import csv
from _common import create_mobile_library_file

## Data extracted using https://maps.norfolk.gov.uk/arcgis/rest/services/layers_ext/where_i_live/MapServer/16/query?f=json&returnGeometry=true&spatialRel=esriSpatialRelIntersects&geometry={"xmin":0.1536,"ymin":52.3553,"xmax":0.9497,"ymax":52.9916,"spatialReference":{"wkid":4326,"latestWkid":4326}}&geometryType=esriGeometryEnvelope&inSR=4326&outFields=*&outSR=4326
DATA_SOURCE_1 = '../raw/norfolk1.json'
# Data extracted using https://maps.norfolk.gov.uk/arcgis/rest/services/layers_ext/where_i_live/MapServer/16/query?f=json&returnGeometry=true&spatialRel=esriSpatialRelIntersects&geometry={"xmin":0.9497,"ymin":52.3553,"xmax":1.7458,"ymax":52.9916,"spatialReference":{"wkid":4326,"latestWkid":4326}}&geometryType=esriGeometryEnvelope&inSR=4326&outFields=*&outSR=4326
DATA_SOURCE_2 = '../raw/norfolk2.json'
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

    CEN_Routes = {
        "CEN117": "1",
        "CEN118": "2",
        "CEN220": "1",
        "CEN222": "2",
        "CEN223": "3",
        "CEN319": "1",
        "CEN320": "2",
        "CEN323": "3",
        "CEN421": "1",
        "CEN422": "2",
        "CEN423": "3",
        "CEN521": "1",
        "CEN522": "2",
        "CEN523": "3",
        "CEN113": "1",
        "CEN213": "1",
        "CEN214": "2",
        "CEN215": "3",
        "CEN313": "1",
        "CEN314": "2",
        "CEN321": "3",
        "CEN413": "1",
        "CEN414": "2",
        "CEN415": "3",
        "CEN513": "1",
        "CEN514": "2",
        "CEN515": "3",
        "CEN114": "1",
        "CEN115": "2",
        "CEN216": "1",
        "CEN217": "2",
        "CEN315": "1",
        "CEN316": "2",
        "CEN416": "1",
        "CEN417": "2",
        "CEN516": "1",
        "CEN517": "2",
        "CEN116": "1",
        "CEN218": "1",
        "CEN219": "2",
        "CEN221": "3",
        "CEN317": "1",
        "CEN318": "2",
        "CEN322": "3",
        "CEN418": "1",
        "CEN419": "2",
        "CEN420": "3",
        "CEN518": "1",
        "CEN519": "2",
        "CEN520": "3"
    }

    four_weeks = timedelta(days=28)
    features = read_data(DATA_SOURCE_1) + read_data(DATA_SOURCE_2)
    features_sorted = sorted(
        features, key=lambda k: k['attributes']['STOP_NUMBE'])
    features_deduped = [i for n, i in enumerate(
        features_sorted) if i not in features_sorted[n + 1:]]

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
