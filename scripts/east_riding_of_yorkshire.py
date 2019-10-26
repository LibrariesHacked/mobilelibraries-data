"""Web scrapes East Riding of Yorkshire's mobile library pages """

from urllib.parse import quote
from datetime import datetime
import json
import os
import csv
import requests
import re
from bs4 import BeautifulSoup

WEBSITE = 'https://www.eastridinglibraries.co.uk/'
LIBRARY_LIST = 'find-a-library/'
DATA_OUTPUT = '../data/east_riding_of_yorkshire.csv'

def run():
    """Runs the main script"""

    mobiles = []
    stop_links = []
    # Get the library list
    stop_list_html = requests.get(WEBSITE + LIBRARY_LIST)
    stop_list_soup = BeautifulSoup(stop_list_html.text, 'html.parser')
    '/find-a-library/?entry=aike_mobile_library '

    for link_tag in stop_list_soup.find_all('a'):
        link = link_tag.get('href')
        if link and '/find-a-library/?entry=' in link and 'mobile_library' in link and link not in stop_links:
            stop_links.append(link)

    for link in stop_links:

        stop_html = requests.get(WEBSITE + link)
        stop_soup = BeautifulSoup(stop_html.text, 'html.parser')

        stop_name = stop_soup.find('h1').text.replace('Mobile Library', '').strip()

        mobiles.append(
            [mobile_library, route, community, stop_name, address, postcode, longitude, latitude,
                day, arrival, departure, 'FREQ=WEEKLY;INTERVAL=4', start, '', timetable]
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
