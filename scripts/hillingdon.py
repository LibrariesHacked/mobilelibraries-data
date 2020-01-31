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
    stops = stop_list_soup.find('div', {'class': 'LBH_MapItems'})

    mobiles.append(
        [mobile_library, route, community, stop_name, address, postcode, longitude, latitude,
            day, 'Public', arrival, departure, 'FREQ=WEEKLY', start, '', '', timetable]
    )

    create_mobile_library_file('Hillingdon', 'hillingdon.csv', mobiles)


run()
