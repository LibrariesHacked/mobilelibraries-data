import json
import geopandas
from datetime import datetime
from shapely.geometry import Point
import re
import csv

DATA_SOURCE = '../raw/angus.geojson'
DATA_OUTPUT = '../data/angus.csv'

def run():

    mobiles = []
    with open(DATA_SOURCE) as data_file:
        data = json.load(data_file)

        features = data['features']
        timetable = 'http://www.angus.gov.uk/sites/angus-cms/files/2019-03/Mobile%20Library%20Route%20Timetable%20Mar%20-%20May%202019.pdf'
        frequency = 2

        dates = {
            1: {
                "Monday": "2019-03-04",
                "Tuesday": "2019-03-05",
                "Wednesday": "2019-03-06",
                "Thursday": "2019-03-07",
                "Friday": "2019-03-08",
            },
            2: {
                "Monday": "2019-03-11",
                "Tuesday": "2019-03-12",
                "Wednesday": "2019-03-13",
                "Thursday": "2019-03-14",
                "Friday": "2019-03-15",
            }
        }

        for feature in features:
            easting = feature['properties']['grid_x']
            northing = feature['properties']['grid_y']

            mobile_library = feature['properties']['vehicle'].title()
            route = feature['properties']['route'].title()
            route = route.replace(mobile_library, '')

            day = feature['properties']['day'].rstrip('s')

            community = ''
            stop_name = feature['properties']['location'].title()
            address = stop_name.title()
            stop_split = stop_name.split(': ')
            
            if len(stop_split) > 1:
                community = stop_split[0].title()
                stop_name = stop_split[1].title()
                address = stop_name + ', ' + community

            arrival = feature['properties']['time_arrive'].replace(':00Z', '')
            departure = feature['properties']['time_depart'].replace(':00Z', '')

            week = feature['properties']['week']

            start = dates[week][day]

            latitude = ''
            longitude = ''

            point = geopandas.GeoSeries([Point(easting, northing)])
            point.crs = {'init': 'epsg:27700'}
            point = point.to_crs({'init': 'epsg:4326'})

            longitude = str(point[0].x)
            latitude = str(point[0].y)

            mobiles.append(
                [mobile_library, route, community, stop_name, address, '', longitude, latitude,
                    day, arrival, departure, 'FREQ=WEEKLY;INTERVAL=2', start, '', timetable]
            )

    with open(DATA_OUTPUT, 'w', encoding='utf8', newline='') as out_csv:
        mob_writer = csv.writer(out_csv, delimiter=',',
                                quotechar='"', quoting=csv.QUOTE_MINIMAL)
        mob_writer.writerow(
            ['organisation', 'mobile', 'route', 'community', 'stop', 'address', 'postcode', 'geox',
             'geoy', 'day', 'arrival', 'departure', 'frequency', 'start', 'end',  'timetable'])
        for sto in mobiles:
            mob_writer.writerow(
                ['Angus', sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])

run()
