"""Web scrapes Northern Ireland mobile library pages """

from datetime import datetime
import json
import os
import csv
import requests
import re
from bs4 import BeautifulSoup
from _common import create_mobile_library_file

WEBSITE = 'https://www.librariesni.org.uk'
LIST_PAGE = '/Libraries/Pages/Mobile-Libraries.aspx'


def run():
    """Runs the main script"""

    dates = {
        '1': {
            "Monday": "2019-04-08",
            "Tuesday": "2019-04-09",
            "Wednesday": "2019-04-10",
            "Thursday": "2019-04-11",
            "Friday": "2019-04-12",
            "Saturday": "2019-04-13"
        },
        '2': {
            "Monday": "2019-04-15",
            "Tuesday": "2019-04-16",
            "Wednesday": "2019-04-17",
            "Thursday": "2019-04-18",
            "Friday": "2019-04-19",
            "Saturday": "2019-04-20"
        }
    }

    mobiles = []

    frequency = 'FREQ=WEEKLY;INTERVAL=2'

    # A single web page listing mobiles
    mobile_list_html = requests.get(WEBSITE + LIST_PAGE)
    mobile_list_soup = BeautifulSoup(mobile_list_html.text, 'html.parser')

    links = mobile_list_soup.find_all('a')

    for link in links:
        href = link.get('href')
        title = link.get('title')
        if title and 'Mobile' in title and 'Mobile' in href and 'Mobile-Libraries' not in href:
            mobile_name = link.string.replace(' Mobile', '')

            url = WEBSITE + href
            mobile_html = requests.get(WEBSITE + href)
            mobile_soup = BeautifulSoup(mobile_html.text, 'html.parser')

            stop_tables = mobile_soup.find_all('table')

            week = None
            day = None
            week_no = None
            for table in stop_tables:

                if table.get('summary') and 'Mobile' in table.get('summary'):
                    for row in table.find_all('tr'):

                        columns = row.find_all('td')
                        # If it's a week/day row then set these
                        if columns and len(columns) > 0 and columns[0] and columns[0].get_text() and 'Week' in columns[0].get_text():
                            dayweek = columns[0].get_text()

                            if dayweek:
                                day = dayweek.split('-')[0].strip().title()
                                week = dayweek.split('-')[1].strip().title()
                                day = ''.join(ch for ch in day if ch.isalnum())
                                week = ''.join(
                                    ch for ch in week if ch.isalnum())
                                week_no = week[-1:]

                            start_date = dates[week_no][day]

                        if len(row.find_all('td')) == 3:

                            address = row.find_all('td')[1].get_text().strip()
                            community = ''
                            stop_name = address.split(', ')[0]
                            if len(address.split(', ')) > 1:
                                community = address.split(', ')[1]

                            postcode = row.find_all('td')[2].get_text().strip()
                            postcode = ''.join(
                                ch for ch in postcode if ch.isalnum())

                            if postcode == 'BT367FT':
                                postcode = 'BT367HT'
                            if postcode == 'BT526NU':
                                postcode = 'BT536NU'
                            if postcode == 'BT52ITU':
                                postcode = 'BT521TU'
                            if postcode == 'BT776BG':
                                postcode = 'BT770BD'
                            if postcode == 'BT459PW':
                                postcode = 'BT359PW'
                            if postcode == 'BT222HN' and stop_name == 'Rathgill George Green Community Centre':
                                postcode = 'BT197TZ'
                            if postcode == 'BT116BB':
                                postcode = 'BT118BB'

                            if postcode and postcode != '':

                                url = 'https://api.postcodes.io/postcodes/' + postcode
                                # then do the geocoding from postcode lookup
                                postcode_request = requests.get(url)
                                postcode_data = json.loads(
                                    postcode_request.text)

                                latitude = postcode_data['result']['latitude']
                                longitude = postcode_data['result']['longitude']

                                if stop_name == '​Montgomery Manor':
                                    latitude = 54.657097
                                    longitude = -5.632655
                                if postcode == 'BT330SE' and stop_name == 'Lawnfield':
                                    latitude = 54.206049
                                    longitude = -5.894022

                                arrival = '12:00'
                                departure = '12:00'
                                route = mobile_name + ' ' + day + ' ' + week_no
                                times = row.find_all(
                                    'td')[0].get_text().strip().replace(':', '')
                                times_matcher = re.compile('\d{1,4}')
                                times_matches = re.findall(
                                    times_matcher, times)
                                if len(times_matches) > 0:
                                    arrival = times_matches[0]
                                    arrival_hours = '00'
                                    arrival_mins = '00'
                                    if len(arrival) == 1:
                                        arrival_hours = arrival.rjust(2, '0')
                                    if len(arrival) == 2:
                                        arrival_hours = arrival
                                    if len(arrival) == 3:
                                        arrival_hours = arrival[0:1].rjust(
                                            2, '0')
                                        arrival_mins = arrival[1:3]
                                    if len(arrival) == 4:
                                        arrival_hours = arrival[0:2]
                                        arrival_mins = arrival[2:4]

                                    if int(arrival_hours) < 8:
                                        arrival_hours = int(arrival_hours) + 12

                                    arrival = str(arrival_hours) + \
                                        ':' + arrival_mins

                                if len(times_matches) > 1:
                                    departure = times_matches[1]
                                    departure_hours = '00'
                                    departure_mins = '00'
                                    if len(departure) == 1:
                                        departure_hours = departure.rjust(
                                            2, '0')
                                    if len(departure) == 2:
                                        departure_hours = departure
                                    if len(departure) == 3:
                                        departure_hours = departure[0:1].rjust(
                                            2, '0')
                                        departure_mins = departure[1:3]
                                    if len(departure) == 4:
                                        departure_hours = departure[0:2]
                                        departure_mins = departure[2:4]

                                    if int(departure_hours) < 8:
                                        departure_hours = int(
                                            departure_hours) + 12

                                    departure = str(
                                        departure_hours) + ':' + departure_mins

                                mobiles.append(
                                    [mobile_name, route, community, stop_name, address, postcode,
                                     longitude, latitude, day, 'Public', arrival, departure, frequency, start_date, '', '',
                                     WEBSITE + href]
                                )

    create_mobile_library_file(
        'Northern Ireland', 'northern_ireland.csv', mobiles)


run()
