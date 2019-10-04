import json
import geopandas
from datetime import datetime
from datetime import timedelta
from dateutil.rrule import rrule, WEEKLY, MO, TU, WE, TH, FR, SA, SU, MONTHLY
from datetime import date
from math import ceil
from shapely.geometry import Point
import re
import csv

# https://my.cambridgeshire.gov.uk/MapGetImage.aspx?MapSource=CCC/AllMaps&RequestType=GeoJSON&ActiveTool=MultiInfo&ActiveLayer=&Layers=moblibrary&ServiceAction=GetMultiInfoFromPoint&Easting=549300&Northing=296900&tolerance=2400000
DATA_SOURCE_MAP = '../raw/cambridgeshire.json'
DATA_SOURCE_STOPS = '../raw/cambridgeshire.csv'
DATA_OUTPUT = '../data/cambridgeshire.csv'

def week_of_month(dt):
    """ Returns the week of the month for the specified date.
    """

    first_day = dt.replace(day=1)

    dom = dt.day
    adjusted_dom = dom + first_day.weekday()

    return int(ceil(adjusted_dom/7.0))

def run():

    timetable = 'https://www.cambridgeshire.gov.uk/residents/libraries-leisure-&-culture/libraries/mobiles/find-a-mobile-library-stop/'
    mobiles = []

    day_codes = {
        'Monday': [MO, 'MO'],
        'Tuesday': [TU, 'TU'],
        'Wednesday': [WE, 'WE'],
        'Thursday': [TH, 'TH'],
        'Friday': [FR, 'FR'],
        'Saturday': [SA, 'SA'],
        'Sunday': [SU, 'SU']
    }

    with open(DATA_SOURCE_STOPS, 'r') as cam_raw:
        mobreader = csv.reader(cam_raw, delimiter=',', quotechar='"')
        next(mobreader, None)  # skip the headers
        for row in mobreader:

            mobile_library = row[0].strip()
            route = row[1].strip()
            week = row[2].strip()
            day = row[3].strip()
            community = row[5].strip()
            stop_name = row[6].strip()
            address = stop_name + ', ' + community
            postcode = row[7].strip()
            frequency = row[8].strip()
            easting = row[9].strip()
            northing = row[10].strip()
            arrival = row[11][0:5].strip()
            departure = row[12][0:5].strip()

            freq = MONTHLY

            repeat_rule = 'FREQ=MONTHLY;BYDAY='
            if '&' in week:
                week = (int(week.split('&')[0].strip()[:1]), int(week.split('&')[1].strip()[:1]))
                repeat_rule = repeat_rule + ','.join(map(lambda x: str(x) + day_codes[day][1], week))
            else:
                week = int(week[:1])
                repeat_rule = repeat_rule + str(week) + day_codes[day][1]

            start = rrule(freq=freq, dtstart=date.today(), bysetpos=week, byweekday=day_codes[day][0], count=1)[0]
            start = start.strftime('%Y-%m-%d')

            latitude = ''
            longitude = ''
            point = geopandas.GeoSeries([Point(float(easting), float(northing))])
            point.crs = {'init': 'epsg:27700'}
            point = point.to_crs(epsg=4326)

            longitude = str(point[0].x)
            latitude = str(point[0].y)

            mobiles.append(
                [mobile_library, route, community, stop_name, address, postcode, longitude, latitude,
                    day, arrival, departure, repeat_rule, start, '', timetable]
            )

    with open(DATA_OUTPUT, 'w', encoding='utf8', newline='') as out_csv:
        mob_writer = csv.writer(out_csv, delimiter=',',
                                quotechar='"', quoting=csv.QUOTE_MINIMAL)
        mob_writer.writerow(
            ['organisation', 'mobile', 'route', 'community', 'stop', 'address', 'postcode', 'geox',
             'geoy', 'day', 'arrival', 'departure', 'frequency', 'start', 'end',  'timetable'])
        
        mobiles_deduped = [i for n, i in enumerate(mobiles) if i not in mobiles[n + 1:]]
        for sto in mobiles_deduped:
            mob_writer.writerow(
                ['Cambridgeshire', sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])

run()
