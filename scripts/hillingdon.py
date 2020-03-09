"""Web scrapes Hillingdon mobile library pages """

from urllib.parse import quote
from datetime import datetime

import csv
import requests
import re
from bs4 import BeautifulSoup
from _common import create_mobile_library_file

WEBSITE = 'https://www-apps.hillingdon.gov.uk/html/apps/ajax/fmn/map.php?dl=md&dd=1&dt=21&dr=50&do=4&ds=1&qx=-0.48896&qy=51.46999&qt=My+location'


def run():
    """Runs the main script"""

    mobiles = []
    mobile_library = 'Mobile'

    # A single web call listing stops
    stop_list_html = requests.get(WEBSITE)
    stop_list_soup = BeautifulSoup(stop_list_html.text, 'html.parser')

    # For each stop get the stop details
    # Being lazy here and just taking the 4th list - can refine another time
    stops = stop_list_soup.find('div', {'class': 'LBH_MapItems'}).text.split('|')[2:]

    for stop in stops:

        stop_data = stop.split('~')

        latitude = stop_data[1]
        longitude = stop_data[2]
        road = stop_data[5]
        day = stop_data[8]
        address = stop_data[7].lstrip(';').replace(';;', ', ')
        stop_name = address.split(', ')[0]
        community = address.split(', ')[0]
        timetable = 'https://archive.hillingdon.gov.uk' + stop_data[9]
        town = community

        # Now use the stop URL to get the rest of the data (cleaner)
        stop_html = requests.get(timetable)
        stop_soup = BeautifulSoup(stop_html.text, 'html.parser')
        stop_table = stop_soup.find('table', {'class': 'LBH_Table'})

        for row in stop_table.find_all('tr'):

            if 'Road' in row.find('th').text:
                road = row.find_all('td')[0].text.strip()
            
            if 'Location' in row.find('th').text:
                stop_name = row.find_all('td')[0].text.strip()

            if 'Town' in row.find('th').text:
                town = row.find_all('td')[0].text.strip()
            
            if 'Area' in row.find('th').text:
                community = row.find_all('td')[0].text.strip()

            if 'Day' in row.find('th').text:  
                day = row.find_all('td')[0].text.strip()

            if 'Arrive' in row.find('th').text:   
                arrival = row.find_all('td')[0].text.strip()

            if 'Depart' in row.find('th').text:   
                departure = row.find_all('td')[0].text.strip()

        address = stop_name + ', ' + road + ', ' + community + ', ' + town

        route = day # will need to manually correct routes after
        start = '' # will manually set start dates later

        mobiles.append(
            [mobile_library, route, community, stop_name, address, '', longitude, latitude,
                day, 'Public', arrival, departure, 'FREQ=WEEKLY', start, '', '', timetable]
        )

    create_mobile_library_file('Hillingdon', 'hillingdon.csv', mobiles)


run()
