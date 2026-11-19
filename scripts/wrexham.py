"""Web scrapes Wrexham County Borough Council mobile library pages (HTML at https://beta.wrexham.gov.uk/service/mobile-library-service) and writes data/wrexham.csv."""

from datetime import datetime
import json
import os
import csv
import requests
import re
from bs4 import BeautifulSoup
from _common import create_mobile_library_file

WEBSITE = 'https://beta.wrexham.gov.uk/'
DATA_SOURCE = 'service/mobile-library-service'
POSTCODE_RE = r'(([Gg][Ii][Rr] 0[Aa]{2})|((([A-Za-z][0-9]{1,2})|(([A-Za-z][A-Ha-hJ-Yj-y][0-9]{1,2})|(([A-Za-z][0-9][A-Za-z])|([A-Za-z][A-Ha-hJ-Yj-y][0-9][A-Za-z]?))))\s?[0-9][A-Za-z]{2}))'
# Matches "Community, Stop (H[:MM] - H[:MM])" where colons and minutes are optional
DATA_RE = r'(.*),(.*)\((\d*):?(\d*).*-[^0-9](\d*):?(\d*)'


def run():
    """Runs the main script"""

    mobiles = []
    mobile_library = 'Mobile 1'

    frequency = 'FREQ=WEEKLY;INTERVAL=3'

    # A single web page listing stops
    url = WEBSITE + DATA_SOURCE
    stop_list_html = requests.get(url)
    stop_list_soup = BeautifulSoup(stop_list_html.text, 'lxml')

    # For each stop get the stop details
    for route in stop_list_soup.find_all('div', {"class": "field-group-accordion-wrapper"}):

        route_name = route.find('h4').string.split('(')[0].strip()
        day = route.find('h4').string.split(
            '(')[1].split(',')[1].replace(')', '').strip()

        stops = route.find_all('ol')[0]

        start = 'Jan 3'
        dates = route.find_all('ul')[0]
        date_list = dates.find_all('li')
        if (date_list[0].string):
            start = dates.find_all('li')[0].string.strip()
        if 'and' in start:
            start = start.split('and')[0]
        # Source page omits the year, so append 2019 to parse month/day
        date_obj = datetime.strptime(start + ' 2019', '%b %d %Y')
        start = datetime.strftime(date_obj, '%Y-%m-%d')

        for stop in stops.find_all('li'):

            # first extract the postcode
            postcode_match = re.compile(POSTCODE_RE).search(stop.string)

            postcode = ''
            if postcode_match:
                postcode = postcode_match.group(1)
            # Hardcoded fixes for missing or typoed postcodes on the source page
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
            stop_str = stop.string.replace(postcode, '').replace('.', ':').replace('–', '-')

            data_match = re.compile(DATA_RE)
            data = data_match.search(stop_str)

            community = data.group(1).strip()
            stop_name = data.group(2).strip()
            arrival_hours = data.group(3).strip()
            # Hours 1-7 denote afternoon (PM) in the 12-hour timetable
            if int(arrival_hours) < 8:
                arrival_hours = int(arrival_hours) + 12
            arrival_mins = data.group(4).strip()
            if arrival_mins == '':
                arrival_mins = '00'
            departure_hours = data.group(5).strip()
            if int(departure_hours) < 8:
                departure_hours = int(departure_hours) + 12
            departure_mins = data.group(6).strip()
            if departure_mins == '':
                departure_mins = '00'
            arrival = str(arrival_hours) + ':' + arrival_mins
            departure = str(departure_hours) + ':' + departure_mins

            address = stop_name + ', ' + community

            mobiles.append(
                [mobile_library, route_name, community, stop_name, address, postcode, longitude, latitude,
                    day, 'Public', arrival, departure, frequency, start, '', '', url]
            )

    create_mobile_library_file('Wrexham', 'wrexham.csv', mobiles)

run()
