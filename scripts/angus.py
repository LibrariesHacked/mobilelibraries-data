import json
import geopandas
from datetime import datetime
from shapely.geometry import Point
import re
import csv
from _common import create_mobile_library_file

DATA_SOURCE = '../raw/angus.geojson'
DATA_OUTPUT = '../data/angus.csv'


def run():

    mobiles = []
    with open(DATA_SOURCE) as data_file:
        data = json.load(data_file)

        features = data['features']
        timetable = 'https://www.angusalive.scot/media/1708/mobile20library20timetable20-20new20service.pdf'

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
            departure = feature['properties']['time_depart'].replace(
                ':00Z', '')

            week = feature['properties']['week']

            route = mobile_library + ' ' + 'Week ' + str(week) + ' ' + day

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
                    day, 'Public', arrival, departure, 'FREQ=WEEKLY;INTERVAL=2', start, '', '', timetable]
            )

    create_mobile_library_file('Angus', 'angus.csv', mobiles)


run()
