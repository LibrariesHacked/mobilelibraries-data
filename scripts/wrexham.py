"""Web scrapes Wrexham mobile library pages """

from datetime import datetime
import json
import os
import csv
import requests
import re
from bs4 import BeautifulSoup
from _common import create_mobile_library_file

WEBSITE = 'http://www.wrexham.gov.uk/'
DATA_SOURCE = 'development/libraries/mobile_library_routes.htm'
POSTCODE_RE = '(([Gg][Ii][Rr] 0[Aa]{2})|((([A-Za-z][0-9]{1,2})|(([A-Za-z][A-Ha-hJ-Yj-y][0-9]{1,2})|(([A-Za-z][0-9][A-Za-z])|([A-Za-z][A-Ha-hJ-Yj-y][0-9][A-Za-z]?))))\s?[0-9][A-Za-z]{2}))'
DATA_RE = '(.*),(.*)\((\d*):(\d*).*[^0-9](\d*):(\d*)'


def run():
    """Runs the main script"""

    mobiles = []
    mobile_library = 'Mobile 1'

    frequency = 'FREQ=WEEKLY;INTERVAL=3'

    # A single web page listing stops
    url = WEBSITE + DATA_SOURCE
    stop_list_html = requests.get(url)
    stop_list_soup = BeautifulSoup(stop_list_html.text, 'html.parser')

    # For each stop get the stop details
    # Being lazy here and just taking the 4th list - can refine another time
    for route in stop_list_soup.find_all('div', 'acc_content'):

        route_name = route.find('h3').string.split('(')[0].strip()
        day = route.find('h3').string.split(
            '(')[1].split(',')[1].replace(')', '').strip()

        stops = route.find_all('ol')[0]

        start = 'Jan 3'
        dates = route.find_all('ul')[0]
        date_list = dates.find_all('li')
        if (date_list[0].string):
            start = dates.find_all('li')[0].string.strip()
        if 'and' in start:
            start = start.split('and')[0]
        date_obj = datetime.strptime(start + ' 2019', '%b %d %Y')
        start = datetime.strftime(date_obj, '%Y-%m-%d')

        for stop in stops.find_all('li'):

            # first extract the postcode
            postcode_match = re.compile(POSTCODE_RE).search(stop.string)

            postcode = ''
            if postcode_match:
                postcode = postcode_match.group(1)
            if postcode == '' and 'Brymbo' in stop.string:
                postcode = 'LL11 5AG'
            if postcode == '' and 'Cynddelw School' in stop.string:
                postcode = 'LL20 7HH'
            if postcode == 'SY13 0GB':
                postcode = 'LL13 0GB'
            if postcode == 'LL11 5GS':
                postcode = 'LL11 5SY'

            # then do the geocoding from postcode lookup
            postcode_request = requests.get(
                'https://api.postcodes.io/postcodes/' + postcode)
            postcode_data = json.loads(postcode_request.text)
            latitude = postcode_data['result']['latitude']
            longitude = postcode_data['result']['longitude']

            # take postcode out of the main string
            stop_str = stop.string.replace(postcode, '').replace('.', ':')

            data_match = re.compile(DATA_RE)
            data = data_match.search(stop_str)

            community = data.group(1).strip()
            stop_name = data.group(2).strip()
            arrival_hours = data.group(3).strip()
            if int(arrival_hours) < 8:
                arrival_hours = int(arrival_hours) + 12
            arrival_mins = data.group(4).strip()
            departure_hours = data.group(5).strip()
            if int(departure_hours) < 8:
                departure_hours = int(departure_hours) + 12
            departure_mins = data.group(6).strip()
            arrival = str(arrival_hours) + ':' + arrival_mins
            departure = str(departure_hours) + ':' + departure_mins

            address = stop_name + ', ' + community

            mobiles.append(
                [mobile_library, route_name, community, stop_name, address, postcode, longitude, latitude,
                    day, 'Public', arrival, departure, frequency, start, '', '', url]
            )

    create_mobile_library_file('Wrexham', 'wrexham.csv', mobiles)

run()
