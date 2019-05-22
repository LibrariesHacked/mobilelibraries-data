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
DATA_SOURCE = 'directory/16/mobile_library_stops?page='
DATA_OUTPUT = '../data/edinburgh.csv'

def run():
    """Runs the main script"""

    mobiles = []
    mobile_library = 'Edinburgh mobile'

    pages = [1, 2, 3, 4]

    dates = {
        "Monday": "2019-05-20",
        "Tuesday": "2019-05-21",
        "Wednesday": "2019-05-22",
        "Thursday": "2019-05-23",
        "Friday": "2019-05-24",
    }

    for page in pages:

        # A single web page listing stops
        stop_list_html = requests.get(WEBSITE + DATA_SOURCE + str(page))
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
                    times = row.find('td').contents[0].replace('.', '')
                    day_matcher = re.compile('(Mon|Tues|Wed|Thurs|Fri)')
                    day = day_matcher.search(times).group(1) + 'day'
                    if (day == 'Wedday'):
                        day = 'Wednesday'
                    times_matcher = re.compile('\d{1,4}')
                    times_matches = re.findall(times_matcher, times)
                    if len(times_matches) > 0:
                        arrival = times_matches[0]
                        arrival_hours = '00'
                        arrival_mins = '00'
                        if len(arrival) == 1:
                            arrival_hours = arrival.rjust(2,'0')
                        if len(arrival) == 2:
                            arrival_hours = arrival
                        if len(arrival) == 3:
                            arrival_hours = arrival[0:1].rjust(2,'0')
                            arrival_mins = arrival[1:3]
                        if len(arrival) == 4:
                            arrival_hours = arrival[0:2]
                            arrival_mins = arrival[2:4]

                        if int(arrival_hours) < 6:
                            arrival_hours = int(arrival_hours) + 12

                        arrival = str(arrival_hours) + ':' + arrival_mins

                    if len(times_matches) > 1:
                        departure = times_matches[1]
                        departure_hours = '00'
                        departure_mins = '00'
                        if len(departure) == 1:
                            departure_hours = departure.rjust(2,'0')
                        if len(departure) == 2:
                            departure_hours = departure
                        if len(departure) == 3:
                            departure_hours = departure[0:1].rjust(2,'0')
                            departure_mins = departure[1:3]
                        if len(departure) == 4:
                            departure_hours = departure[0:2]
                            departure_mins = departure[2:4]

                        if int(departure_hours) < 6:
                            departure_hours = int(departure_hours) + 12

                        departure = str(departure_hours) + ':' + departure_mins

                    route = day
                    start = dates[day]

                if 'Address' in row_header:
                    address = row.find('td').contents[0].strip()

                if 'Postcode' in row_header:
                    postcode = row.find('td').contents[0].strip()

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
