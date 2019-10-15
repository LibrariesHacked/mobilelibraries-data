import json
from datetime import datetime
import re
import csv

DATA_SOURCE = '../raw/north_lincolnshire.geojson'
DATA_OUTPUT = '../data/north_lincolnshire.csv'


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
                ['North Lincolnshire', sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])


run()
