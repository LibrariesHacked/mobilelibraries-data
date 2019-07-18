"""Web scrapes Warwickshire mobile library pages """

from urllib.parse import quote
from datetime import datetime
import json
import os
import csv
import requests
import re
from bs4 import BeautifulSoup

WEBSITE = 'https://apps.warwickshire.gov.uk'
LOCATIONS_SOURCE = '/MobileLibraries/locations'
DATA_OUTPUT = '../data/warwickshire.csv'


def run():
    """Runs the main script"""

    organisation = 'Warwickshire'

    mobiles = []

    alphabet_list_html = requests.get(WEBSITE + LOCATIONS_SOURCE)
    alphabet_list_soup = BeautifulSoup(alphabet_list_html.text, 'html.parser')

    for alphabet_link in alphabet_list_soup.find('ul', {"class": "alphabet_group_links"}).find_all('a'):

        stop_list_html = requests.get(WEBSITE + alphabet_link.get('href'))
        stop_list_soup = BeautifulSoup(stop_list_html.text.replace('</td>', ''), 'html.parser')

        for stop_link in stop_list_soup.find('ul', {"class": "index-list"}).find_all('a'):

            stop_html = requests.get(WEBSITE + stop_link.get('href'))
            stop_soup = BeautifulSoup(stop_html.text, 'html.parser')

            location_result = re.search(r'"lat":"(\d+\.\d+)","lng":"(-\d.\d+)"', stop_html.text)
            times_result = re.search(r'The Mobile library will be here from\n\s+(\d+:\d+)\n\s+to\n\s+(\d+:\d+)', stop_html.text)
            
            arrival = times_result.group(1)
            departure = times_result.group(2)

            longitude = location_result.group(2)
            latitude = location_result.group(1)

            route_mobile = stop_soup.find('h3').find('a').string.split(' ')
            mobile = route_mobile[0]
            route = route_mobile[1]

            title = stop_link.string
            titles = title.split('-')
            stop_name = titles[1].strip()
            community = titles[0].strip()

            address = stop_name + ', ' + community

            dates = stop_soup.find('ul', {"class": "travel_day_list"}).find_all('li')

            start_str = dates[0].string.strip()
            date = datetime.strptime(start_str, '%d %B %Y')
            start = date.strftime('%Y-%m-%d')
            
            end_str = dates[len(dates) - 1].string.strip()
            date = datetime.strptime(end_str, '%d %B %Y')
            end = date.strftime('%Y-%m-%d')

            day = date.strftime('%A')

            timetable = WEBSITE + stop_link.get('href')

            mobiles.append(
                    [mobile, route, community, stop_name, address, '', longitude, latitude,
                     day, arrival, departure, 'FREQ=WEEKLY;INTERVAL=3', start, end, timetable]
                )

    with open(DATA_OUTPUT, 'w', encoding='utf8', newline='') as out_csv:
        mob_writer = csv.writer(out_csv, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        mob_writer.writerow(
            ['organisation', 'mobile', 'route', 'community', 'stop', 'address', 'postcode', 'geox',
             'geoy', 'day', 'arrival', 'departure', 'frequency', 'start', 'end',  'timetable'])
        for sto in mobiles:
            mob_writer.writerow(
                [organisation, sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])


run()
