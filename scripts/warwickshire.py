"""Web scrapes Warwickshire mobile library pages """

from urllib.parse import quote
from datetime import datetime
import json
import os
import csv
import requests
import re
from bs4 import BeautifulSoup
from _common import create_mobile_library_file

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
        stop_list_soup = BeautifulSoup(
            stop_list_html.text.replace('</td>', ''), 'html.parser')

        for stop_link in stop_list_soup.find('ul', {"class": "index-list"}).find_all('a'):

            stop_html = requests.get(WEBSITE + stop_link.get('href'))
            stop_soup = BeautifulSoup(stop_html.text, 'html.parser')

            location_result = re.search(
                r'"lat":"(\d+\.\d+)","lng":"(-\d.\d+)"', stop_html.text)
            times_result = re.search(
                r'The Mobile library will be here from\n\s+(\d+:\d+)\n\s+to\n\s+(\d+:\d+)', stop_html.text)

            arrival = times_result.group(1)
            departure = times_result.group(2)

            route_mobile = stop_soup.find('h3').find('a').string.split(' ')
            mobile = route_mobile[0]
            route = route_mobile[1]

            title = stop_link.string
            titles = title.split('-')
            stop_name = titles[1].strip()
            community = titles[0].strip()

            if 'Wren Day Nursery' in stop_name:
                longitude = '-1.5308972'
                latitude = '52.3390278'
            else:
                longitude = location_result.group(2)
                latitude = location_result.group(1)

            address = stop_name + ', ' + community

            dates = stop_soup.find(
                'ul', {"class": "travel_day_list"}).find_all('li')

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
                 day, 'Public', arrival, departure, 'FREQ=WEEKLY;INTERVAL=3', start, '', '', timetable]
            )

    create_mobile_library_file(organisation, 'warwickshire.csv', mobiles)


run()
