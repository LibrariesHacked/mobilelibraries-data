import json
from datetime import datetime
import re
import csv
from _common import create_mobile_library_file

DATA_SOURCE = '../raw/north_lincolnshire.geojson'


def run():

    mobiles = []
    with open(DATA_SOURCE) as data_file:
        data = json.load(data_file)

        features = data['features']
        timetable = 'https://www.northlincs.gov.uk/schools-libraries-and-learning/libraries/the-mobile-library/'

        dates = {
            12: '8/01/2019',
            11: '21/01/2019',
            13: '23/01/2019',
            14: '24/01/2019',
            15: '25/01/2019',
            16: '26/01/2019',
            21: '28/01/2019',
            23: '9/01/2019',
            24: '10/01/2019',
            26: '12/01/2019',
            31: '14/01/2019',
            33: '16/01/2019',
            34: '17/01/2019',
            35: '18/01/2019',
            36: '19/01/2019'
        }

        for feature in features:

            frequency = 'FREQ=WEEKLY;INTERVAL=3'
            route_id = feature['properties']['id']
            if route_id == 12:
                frequency = 'FREQ=WEEKLY;INTERVAL=1'
            route_name = 'Route ' + str(route_id)
            day = feature['properties']['day']
            address = feature['properties']['addr']
            arrival = feature['properties']['time1'][:5]
            departure = feature['properties']['time2'][:5]
            community = feature['properties']['name']
            stop_name = feature['properties']['addr']

            longitude = feature['geometry']['coordinates'][0]
            latitude = feature['geometry']['coordinates'][1]

            date = datetime.strptime(dates[route_id], '%d/%m/%Y')
            start = date.strftime('%Y-%m-%d')

            mobiles.append(
                ['Mobile', route_name, community, stop_name, address, '', longitude, latitude,
                    day, 'Public', arrival, departure, frequency, start, '', '', timetable]
            )

    create_mobile_library_file(
        'North Lincolnshire', 'north_lincolnshire.csv', mobiles)


run()
