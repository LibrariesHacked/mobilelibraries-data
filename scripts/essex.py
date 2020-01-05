"""Web scrapes Essex mobile library pages """

from urllib.parse import quote
from datetime import datetime
import json
import os
import csv
import requests
import re
import time
import os.path
import base64
from os import path
from bs4 import BeautifulSoup
from _common import create_mobile_library_file

WEBSITE = 'https://libraries.essex.gov.uk/'
ROUTES_LIST = 'mobile-library-service/mobile-routes-and-areas-april-2018/'


def run():
    """Runs the main script"""
    mobiles = []

    route_list_html = requests.get(WEBSITE + ROUTES_LIST)
    route_list_soup = BeautifulSoup(route_list_html.text, 'html.parser')

    route_links = []
    for link in route_list_soup.find_all('a'):
        if 'mobile-library-route' in link.get('href'):
            route_links.append(link.get('href'))

    for link in route_links:
        route_text = ''
        route_encoded_link = str(
            base64.urlsafe_b64encode(link.encode("utf-8")), 'utf-8')
        if not path.exists('../raw/essex/' + route_encoded_link + '.txt'):
            route_html = requests.get(link)
            route_text = route_html.text
            # save the data out as web scraping seems to be getting blocked so may take a few goes
            route_file = open('../raw/essex/' +
                              route_encoded_link + '.txt', "w")
            route_file.write(route_text)
            route_file.close()
            time.sleep(10)
        else:
            route_text = open('../raw/essex/' +
                              route_encoded_link + '.txt', 'r').read()

        route_soup = BeautifulSoup(route_text, 'html.parser')

        stop_links = []
        for stop_link in route_soup.find_all('table')[0].find_all('a'):
            stop_links.append(WEBSITE + stop_link.get('href'))

        for stop in stop_links:
            stop_text = ''
            stop_encoded_link = str(base64.urlsafe_b64encode(
                stop.encode("utf-8")), 'utf-8')
            if not path.exists('../raw/essex/' + stop_encoded_link + '.txt'):
                stop_html = requests.get(stop)
                stop_text = stop_html.text
                stop_file = open('../raw/essex/' +
                                 stop_encoded_link + '.txt', "w")
                stop_file.write(stop_text)
                stop_file.close()
            else:
                stop_text = open('../raw/essex/' +
                                 stop_encoded_link + '.txt', 'r').read()

            stop_soup = BeautifulSoup(stop_text, 'html.parser')
            values = stop_soup.find_all('div', {"class": "pfont"})
            stop_name = stop_soup.find_all(
                'div', {"class": "yellow-wrapper"})[0].find("h1").text
            community = values[0].text.strip().splitlines()[0].strip()
            address = stop_name + ', ' + community
            postcode = values[0].text.strip().splitlines()[-1].strip()
            if postcode == 'CM133AS':
                postcode = 'CM132AS'
            if postcode == 'RM4 1ED':
                postcode = 'RM4 1LU'
            frequency = 'FREQ=WEEKLY;INTERVAL=' + values[1].text.strip()[:1]
            day = values[2].text.strip()
            times = values[3].text.strip()
            route_mobile = values[4].text.strip()
            route = 'Week ' + route_mobile.split('week')[1].strip() + ' ' + day
            mobile_library = route_mobile.split('week')[0].strip()
            start = values[6].text.strip()
            start = datetime.strptime(start, '%d %B %Y')
            start = start.strftime('%Y-%m-%d')
            arrival = times.split('to')[0].replace('am', '').replace(
                'pm', '').strip().replace('.', '')

            arrival_hours = '00'
            arrival_mins = '00'
            if len(arrival) == 1:
                arrival_hours = arrival.rjust(2, '0')
            if len(arrival) == 2:
                arrival_hours = arrival
            if len(arrival) == 3:
                arrival_hours = arrival[0:1].rjust(2, '0')
                arrival_mins = arrival[1:3]
            if len(arrival) == 4:
                arrival_hours = arrival[0:2]
                arrival_mins = arrival[2:4]

            if int(arrival_hours) < 8:
                arrival_hours = int(arrival_hours) + 12

            arrival = str(arrival_hours) + ':' + arrival_mins

            departure = times.split('to')[1].replace(
                'am', '').replace('pm', '').strip().replace('.', '')

            departure_hours = '00'
            departure_mins = '00'
            if len(departure) == 1:
                departure_hours = departure.rjust(2, '0')
            if len(departure) == 2:
                departure_hours = departure
            if len(departure) == 3:
                departure_hours = departure[0:1].rjust(2, '0')
                departure_mins = departure[1:3]
            if len(departure) == 4:
                departure_hours = departure[0:2]
                departure_mins = departure[2:4]

            if int(departure_hours) < 8:
                departure_hours = int(departure_hours) + 12

            departure = str(departure_hours) + ':' + departure_mins

            url = 'https://api.postcodes.io/postcodes/' + postcode
            postcode_request = requests.get(url)
            postcode_data = json.loads(postcode_request.text)
            latitude = postcode_data['result']['latitude']
            longitude = postcode_data['result']['longitude']

            mobiles.append(
                [mobile_library, route, community, stop_name, address, postcode, longitude, latitude,
                 day, 'Public', arrival, departure, frequency, start, '', '', stop]
            )

    create_mobile_library_file('Essex', 'essex.csv', mobiles)


run()
