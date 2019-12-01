"""Web scrapes East Riding of Yorkshire's mobile library pages """

from urllib.parse import quote
from datetime import datetime
import os
import csv
import re
from bs4 import BeautifulSoup

# HTML obtained using curl

HTML = '../raw/east_riding_of_yorkshire.html'
DATA_OUTPUT = '../data/east_riding_of_yorkshire.csv'


def run():
    """Runs the main script"""

    mobiles = []
    mobile_library = 'Mobile'

    route_names = {}

    route_number = 0

    stop_soup = BeautifulSoup(open(HTML), "html.parser")

    for venue in stop_soup.find_all('div', {"class": "er-filter-block-wrapper"}):

        venue_type = venue.find(
            'div', {"data-id": "venue_type"}).find('div', {"class": "content"}).get_text()

        if (venue_type) == 'Library_All/Library_Mobile Library':

            stop_name = venue.find('div', {"data-id": "name"}).find(
                'div', {"class": "content"}).find('a').get_text().replace(' Mobile Library', '')
            community = stop_name
            postcode = venue.find(
                'div', {"data-id": "postcode"}).find('div', {"class": "content"}).get_text()
            address = stop_name + ', ' + postcode
            latitude = venue.find(
                'div', {"data-id": "latitude"}).find('div', {"class": "content"}).get_text()
            longitude = venue.find(
                'div', {"data-id": "longitude"}).find('div', {"class": "content"}).get_text()
            timetable = 'https://www.eastridinglibraries.co.uk' + \
                venue.find('div', {"data-id": "learn_more"}).find('div',
                                                                  {"class": "content"}).find('a').get('href').strip()

            openings = venue.find(
                'div', {"data-id": "opening_times"}).find('div', {"class": "content"}).get_text().split(';')

            opening_times = ''
            for entry in openings:
                if '2019' in entry:
                    opening_times = entry

            times_result = re.search(
                r'(\d{1,2}\.{0,1}\d{1,2})-(\d{1,2}\.{0,1}\d{1,2})', opening_times)
            arrival = times_result.group(1).replace('.', ':')
            if len(arrival) < 3:
                arrival = arrival + ':00'
            if (len(arrival.split(':')[1])) < 2:
                arrival = arrival + '0'
            departure = times_result.group(2).replace('.', ':')
            if len(departure) < 3:
                departure = departure + ':00'
            if (len(departure.split(':')[1])) < 2:
                departure = departure + '0'
            date_result = re.search(r'(2019\d{4})', opening_times)
            start = datetime.strptime(date_result.group(1), '%Y%m%d')
            day = start.strftime('%A')
            start = start.strftime('%Y-%m-%d')

            frequency_result = re.search(r'2019\d{4}(\d)', opening_times)
            frequency = 'FREQ=WEEKLY;INTERVAL=' + frequency_result.group(1)
            if not route_names.get(start):
                route_number = route_number + 1
                route_names[start] = route_number

            route = route_names[start]

            mobiles.append(
                [mobile_library, route, community, stop_name, address, postcode, longitude, latitude,
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
                ['East Riding of Yorkshire', sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])


run()
