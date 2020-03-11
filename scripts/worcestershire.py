"""Web scrapes Worcestershire mobile library pages """

from urllib.parse import quote
import os
import csv
import requests
import re
from bs4 import BeautifulSoup
from dateutil.rrule import rrule, WEEKLY, MO, TU, WE, TH, FR, SA, SU, MONTHLY
from datetime import date
from datetime import datetime
from _common import create_mobile_library_file

WEBSITE = 'http://www.worcestershire.gov.uk/'
A_Z_PAGE = 'directory/54/a_to_z'

day_codes = {
    'Monday': [MO, 'MO'],
    'Tuesday': [TU, 'TU'],
    'Wednesday': [WE, 'WE'],
    'Thursday': [TH, 'TH'],
    'Friday': [FR, 'FR'],
    'Saturday': [SA, 'SA'],
    'Sunday': [SU, 'SU']
}

def run():
    """Runs the main script"""

    mobiles = []
    mobile_library = 'Mobile'

    # Get the A-Z links
    az_list_html = requests.get(WEBSITE + A_Z_PAGE)
    az_list_soup = BeautifulSoup(az_list_html.text, 'html.parser')

    for az_link in az_list_soup.find('ul', {'class': 'item-list item-list__inline a-to-z' }).find_all('a'):

        # A single web page listing stops for the alphabet letter
        stop_list_html = requests.get(WEBSITE + az_link.get('href'))
        stop_list_soup = BeautifulSoup(stop_list_html.text, 'html.parser')

        # For each stop get the stop details
        for link in stop_list_soup.find_all('ul', {'class': 'item-list'})[2].find_all('a'):

            community = link.text.replace(' Mobile Library Timetable', '')
            stop_url = link.get('href')
            
            stop_html = requests.get(WEBSITE + stop_url)
            stop_soup = BeautifulSoup(stop_html.text, 'html.parser')
            stop_rows = stop_soup.find('div', {'class': 'editor'}).text.splitlines()

            stop_schedule = stop_soup.find('table', {'class': 'data-table directory-record'}).find_all('td')[0].text
            schedule_matcher = re.compile(r'(\d)(st|nd|rd|th) (.*day)')
            schedule_search = schedule_matcher.search(stop_schedule)

            week = int(schedule_search.group(1))
            day = schedule_search.group(3)

            start = rrule(freq=MONTHLY, dtstart=date.today(), bysetpos=week, byweekday=day_codes[day][0], count=1)[0]
            start = start.strftime('%Y-%m-%d')
            repeat_rule = 'FREQ=MONTHLY;BYDAY=' + str(week) + day_codes[day][1]

            route = day + ' Week ' + str(week)

            location = stop_soup.find(id='map_marker_location_10798').get('value')
            longitude = location.split(',')[1]
            latitude = location.split(',')[0]

            for stop in stop_rows:

                if (community in stop):

                    stop_times_matcher = re.compile(r'(\d{1,2}:\d{2}).*?(\d{1,2}:\d{2})(.*)')
                    times_result = re.search(stop_times_matcher, stop)
                    arrival = times_result.group(1)
                    departure = times_result.group(2)
                    stop_name = times_result.group(3).replace(community, '').replace(',', '').replace('-', '').strip()
                    address = stop_name + ', ' + community

                    mobiles.append(
                        [mobile_library, route, community, stop_name, address, '', longitude, latitude,
                        day, 'Public', arrival, departure, repeat_rule, start, '', '', WEBSITE + stop_url]
                    )

    create_mobile_library_file('Worcestershire', 'worcestershire.csv', mobiles)

run()
