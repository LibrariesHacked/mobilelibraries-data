"""Web scrapes Ediburgh mobile library pages """

from urllib.parse import quote
from datetime import datetime
import json
import os
import csv
import requests
import re
from bs4 import BeautifulSoup

WEBSITE = 'https://www.edinburgh.gov.uk/'
DATA_SOURCE = 'directory/16/mobile_library_stops'
DATA_OUTPUT = '../data/edinburgh.csv'

def run():
    """Runs the main script"""

    mobiles = []
    mobile_library = 'Edinburgh mobile'

    dates = {
        "Monday": "2019-04-08",
        "Tuesday": "2019-04-09",
        "Wednesday": "2019-04-10",
        "Thursday": "2019-04-11",
        "Friday": "2019-04-12",
    }

    # A single web page listing stops
    stop_list_html = requests.get(WEBSITE + DATA_SOURCE)
    stop_list_soup = BeautifulSoup(stop_list_html.text, 'html.parser')

    # For each stop get the stop details
    # Being lazy here and just taking the 4th list - can refine another time
    for link in stop_list_soup.find_all('ul')[3].find_all('a'):

        stop_name = link.string
        stop_url = link.get('href')
        stop_html = requests.get(WEBSITE + stop_url)
        stop_soup = BeautifulSoup(stop_html.text, 'html.parser')

        community = ''
        arrival = ''
        departure = ''
        day = ''
        route = ''
        location = stop_soup.find(id='map_marker_location_197').get('value')
        longitude = location.split(',')[1]
        latitude = location.split(',')[0]
        timetable = WEBSITE + stop_url

        data_table = stop_soup.find_all('table')[0]
        for row in data_table.find_all('tr'):
            row_header = row.find('th').string.strip()

            if 'Day' in row_header:
                times = row.find('td').contents[0]
                day_matcher = re.compile('(Mon|Tues|Wednes|Thurs|Fri)')
                day = day_matcher.search(times).group(1) + 'day'
                times_matcher = re.compile('(\d*\.\d*)* - (\d*\.\d*)*')
                times_matches = times_matcher.search(times)
                arrival = times_matches.group(1)
                if arrival:
                    arrival = arrival.replace('.', ':')
                departure = times_matches.group(2).replace('.', ':')
                if departure:
                    departure = departure.replace('.', ':')
                route = day
                start = dates[day]

            if 'Address' in row_header:
                address = data_table.find_all('tr')[1].find_all('td')[0].string.strip()

            if 'Postcode' in row_header:
                postcode = data_table.find_all(
                    'tr')[1].find_all('td')[0].string.strip()

        mobiles.append(
            [mobile_library, route, community, stop_name, address, postcode, longitude, latitude,
             day, arrival, departure, 'FREQ=WEEKLY', start, '', timetable
             ])

    with open(DATA_OUTPUT, 'w', encoding='utf8', newline='') as out_csv:
        mob_writer = csv.writer(out_csv, delimiter=',',
                                quotechar='"', quoting=csv.QUOTE_MINIMAL)
        mob_writer.writerow(
            ['organisation', 'mobile', 'route', 'community', 'stop', 'address', 'postcode', 'geox',
             'geoy', 'day', 'arrival', 'departure', 'frequency', 'start', 'end',  'timetable'])
        for sto in mobiles:
            mob_writer.writerow(
                ['Edinburgh', sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])


run()
