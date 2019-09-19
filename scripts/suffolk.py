"""Web scrapes Suffolk mobile library pages """

from urllib.parse import quote
from datetime import datetime
import json
import os
import csv
import requests
import re
from bs4 import BeautifulSoup

WEBSITE = 'https://www.suffolklibraries.co.uk/'
ROUTES = 'mobiles-home/mobile-route-schedules/'
DATA_OUTPUT = '../data/suffolk.csv'


def run():
    """Runs the main script"""

    mobiles = []

    route_list_html = requests.get(WEBSITE + ROUTES)
    route_list_soup = BeautifulSoup(route_list_html.text, 'html.parser')

    route_links = []
    for li in route_list_soup.find_all('li'):
        if li.find('a') is not None and li.find('a').get('title') is not None and 'Mobile Library Route' in li.find('a').get('title'):
            title = li.text.strip()
            route_links.append({
                'href': li.find('a').get('href'),
                'day': title.split(' ')[2],
                'route': title.split(' ')[0] + ' ' + title.split(' ')[1]
            })

    for route_link in route_links:

        # A single web page listing stops
        stop_list_html = requests.get(WEBSITE + str(route_link['href']))
        stop_list_soup = BeautifulSoup(stop_list_html.text, 'html.parser')

        route_title = stop_list_soup.find('h1').text.strip()
        mobile_library = route_title.split(' Mobile Library ')[0]

        paras = stop_list_soup.find_all('p')
        dates = []
        for para in paras:
            if '2019:' in para.text:
                dates = para.text.strip().split(', ')
        
        date = datetime.strptime(dates[2] + ' 2019', '%d %B %Y')
        start = date.strftime('%Y-%m-%d')

        # For each stop get the stop details
        for stop in stop_list_soup.find_all('tr')[1:]:

            route = route_link['route']
            community = stop.find_all('td')[2].string.strip()
            stop_name = stop.find_all('td')[1].string.strip()
            address = stop_name + ', ' + community
            postcode = ''
            longitude = ''
            latitude = ''
            day = route_link['day'][:-1]
            times = re.sub(r'\D', '', stop.find_all('td')[3].text)
            arrival = times[:2] + ':' + times[2:4]
            departure = times[4:6] + ':' + times[6:]
            start = ''
            timetable = WEBSITE + route_link['href']

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
                ['Suffolk', sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])


run()
