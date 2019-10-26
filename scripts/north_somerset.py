"""Converts raw North Somerset data to standardised mobile library format"""

import csv
import geopandas
from datetime import datetime
from shapely.geometry import Point

DATA_SOURCE = '../raw/north_somerset.csv'
DATA_OUTPUT_NS = '../data/north_somerset.csv'
DATA_OUTPUT_SG = '../data/south_gloucestershire.csv'


def run():
    """Runs the main script"""
    mobiles_ns = []
    mobiles_sg = []
    timetable_ns = 'https://www.n-somerset.gov.uk/my-services/leisure/libraries/bringing-the-library-to-you/mobile-library/'
    timetable_sg = 'https://www.southglos.gov.uk/libraries/mobile-library-almondsbury-severn-beach-pilning/'
    mobile_library = 'Mobile'

    with open(DATA_SOURCE, 'r') as northsom_raw:
        mobreader = csv.reader(northsom_raw, delimiter=',', quotechar='"')
        next(mobreader, None)  # skip the headers
        for row in mobreader:
            route = row[0].strip()
            community = row[1].strip()
            stop_name = row[2].strip()
            frequency = 'FREQ=WEEKLY;INTERVAL=2'
            day = row[4].strip()
            arrival = row[5].strip()
            departure = row[6].strip()
            start = row[7].strip()
            
            easting = float(row[8].strip())
            northing = float(row[9].strip())
            point = geopandas.GeoSeries([Point(easting, northing)])
            point.crs = {'init': 'epsg:27700'}
            point = point.to_crs({'init': 'epsg:4326'})
            longitude = str(point[0].x)
            latitude = str(point[0].y)
            address = stop_name + ', ' + community

            if route == 'Thursday 1':
                mobiles_sg.append(
                    [mobile_library, route, community, stop_name, address, '', longitude, latitude,
                        day, arrival, departure, frequency, start, '', timetable_sg]
                )
            else:
                mobiles_ns.append(
                    [mobile_library, route, community, stop_name, address, '', longitude, latitude,
                        day, arrival, departure, frequency, start, '', timetable_ns]
                )

    with open(DATA_OUTPUT_NS, 'w', encoding='utf8', newline='') as out_csv:
        mob_writer = csv.writer(out_csv, delimiter=',',
                                quotechar='"', quoting=csv.QUOTE_MINIMAL)
        mob_writer.writerow(
            ['organisation', 'mobile', 'route', 'community', 'stop', 'address', 'postcode', 'geox',
             'geoy', 'day', 'arrival', 'departure', 'frequency', 'start', 'end',  'timetable'])
        for sto in mobiles_ns:
            mob_writer.writerow(
                ['North Somerset', sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])

    with open(DATA_OUTPUT_SG, 'w', encoding='utf8', newline='') as out_csv:
        mob_writer = csv.writer(out_csv, delimiter=',',
                                quotechar='"', quoting=csv.QUOTE_MINIMAL)
        mob_writer.writerow(
            ['organisation', 'mobile', 'route', 'community', 'stop', 'address', 'postcode', 'geox',
             'geoy', 'day', 'arrival', 'departure', 'frequency', 'start', 'end',  'timetable'])
        for sto in mobiles_sg:
            mob_writer.writerow(
                ['South Gloucestershire', sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])


run()
