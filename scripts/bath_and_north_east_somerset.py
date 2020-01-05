import json
from datetime import datetime, timedelta
import re
import csv
import geopandas
from shapely.geometry import Point
from _common import create_mobile_library_file

## Data extracted using https://isharemaps.bathnes.gov.uk/MapGetImage.aspx?Type=json&MapSource=BathNES/banes&RequestType=GeoJSON&ServiceAction=ShowMyClosest&ActiveTool=MultiInfo&ActiveLayer=MobileLibraryStops&SearchType=findMyNearest&Distance=180047&MaxResults=500&Easting=375973&Northing=166129
DATA_SOURCE = '../raw/bath_and_north_east_somerset.json'
TIMETABLE = 'https://beta.bathnes.gov.uk/mobile-library-routes'

def read_data(data_source):

    features = []
    with open(data_source) as data_file:
        data = json.load(data_file)
        for feature in data[0]['features']:
            features.append(feature)

    return features

def run():

    features = read_data(DATA_SOURCE)

    mobiles = []
    organisation = 'Bath and North East Somerset'
    mobile_name = 'Mobile'
    frequency = 'FREQ=WEEKLY;INTERVAL=2'
    dates = {
        "Route 1": "2019-10-14",
        "Route 2": "2019-10-15",
        "Route 3": "2019-10-16",
        "Route 4": "2019-10-17",
        "Route 5": "2019-10-18",
        "Route 6": "2019-10-21",
        "Route 7": "2019-10-22",
        "Route 8": "2019-10-23",
        "Route 9": "2019-10-24"
    }

    for feature in features:

        route = feature['properties']['fields']['day_number'].replace('Day', 'Route')
        stop_name = feature['properties']['fields']['stop']
        community = feature['properties']['fields']['village']
        if stop_name == '':
            stop_name = community
        address = stop_name + ', ' + community
        day = feature['properties']['fields']['day']
        time = feature['properties']['fields']['time']
        arrival = time.split('-')[0].strip().replace('.', ':')
        departure = time.split('-')[-1].strip().replace('.', ':')
        start = ''
        if community != 'LIBRARY DEPOT':
            start = dates[route]

        easting = feature['geometry']['coordinates'][0][0]
        northing = feature['geometry']['coordinates'][0][1]

        latitude = ''
        longitude = ''
        point = geopandas.GeoSeries([Point(float(easting), float(northing))])
        point.crs = {'init': 'epsg:27700'}
        point = point.to_crs(epsg=4326)
        
        longitude = str(point[0].x)
        latitude = str(point[0].y)

        if community != 'LIBRARY DEPOT':
            mobiles.append(
                [mobile_name, route, community, stop_name, address, '', longitude, latitude,
                    day, 'Public', arrival, departure, frequency, start, '', '', TIMETABLE]
            )

    create_mobile_library_file(organisation, 'bath_and_north_east_somerset.csv', mobiles)

run()
