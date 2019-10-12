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

WEBSITE = 'https://libraries.essex.gov.uk/'
ROUTES_LIST = 'mobile-library-service/mobile-routes-and-areas-april-2018/'
DATA_OUTPUT = '../data/essex.csv'


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
        route_encoded_link = str(base64.urlsafe_b64encode(link.encode("utf-8")), 'utf-8')
        if not path.exists('../raw/essex/' + route_encoded_link + '.txt'):
            route_html = requests.get(link)
            route_text = route_html.text
            # save the data out as web scraping seems to be getting blocked so may take a few goes
            route_file = open('../raw/essex/' + route_encoded_link + '.txt', "w")
            route_file.write(route_text)
            route_file.close()
            time.sleep(10)
        else:
            route_text = open ('../raw/essex/' + route_encoded_link + '.txt', 'r').read()

        route_soup = BeautifulSoup(route_text, 'html.parser')

        stop_links = []
        for stop_link in route_soup.find_all('table')[0].find_all('a'):
            stop_links.append(WEBSITE + stop_link.get('href'))

        for stop in stop_links:
            stop_text = ''
            stop_encoded_link = str(base64.urlsafe_b64encode(stop.encode("utf-8")), 'utf-8')
            if not path.exists('../raw/essex/' + stop_encoded_link + '.txt'):
                stop_html = requests.get(stop)
                stop_text = stop_html.text
                stop_file = open('../raw/essex/' + stop_encoded_link + '.txt', "w")
                stop_file.write(stop_text)
                stop_file.close()
            else:
                stop_text = open ('../raw/essex/' + stop_encoded_link + '.txt', 'r').read()

            stop_soup = BeautifulSoup(stop_text, 'html.parser')
            values = stop_soup.find_all('div', {"class": "pfont"})
            stop_name = stop_soup.find_all(
                'div', {"class": "yellow-wrapper"})[0].find("h1").text
            community = values[0].text.strip().splitlines()[0].strip()
            address = stop_name + ', ' + community
            postcode = values[0].text.strip().splitlines()[-1].strip()
            frequency = 'FREQ=WEEKLY;INTERVAL=' + values[1].text.strip()[:1]
            day = values[2].text.strip()
            times = values[3].text.strip()
            route = values[4].text.strip()
            route = 'Week ' + route.split('week')[1].strip()
            mobile_library = route.split('week')[0].strip()
            start = values[6].text.strip()
            start = datetime.strptime(start, '%d %B %Y')
            start = start.strftime('%Y-%m-%d')
            arrival = times.split('to')[0].replace('am', '').replace(
                'pm', '').strip().replace('.', ':')
            departure = times.split('to')[1].replace(
                'am', '').replace('pm', '').strip().replace('.', ':')

            url = 'https://api.postcodes.io/postcodes/' + postcode
            #postcode_request = requests.get('https://api.postcodes.io/postcodes/' + postcode)
            #postcode_data = json.loads(postcode_request.text)
            latitude = ''#postcode_data['result']['latitude']
            longitude = ''#postcode_data['result']['longitude']
            
            mobiles.append(
                [mobile_library, route, community, stop_name, address, postcode, longitude, latitude,
                 day, arrival, departure, frequency, start, '', stop]
            )

    with open(DATA_OUTPUT, 'w', encoding='utf8', newline='') as out_csv:
        mob_writer = csv.writer(out_csv, delimiter=',',
                                quotechar='"', quoting=csv.QUOTE_MINIMAL)
        mob_writer.writerow(
            ['organisation', 'mobile', 'route', 'community', 'stop', 'address', 'postcode', 'geox',
             'geoy', 'day', 'arrival', 'departure', 'frequency', 'start', 'end',  'timetable'])
        for sto in mobiles:
            mob_writer.writerow(
                ['Essex', sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])


run()
