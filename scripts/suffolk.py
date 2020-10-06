"""Web scrapes Suffolk mobile library pages """

from urllib.parse import quote
from datetime import datetime
import json
import os
import csv
import requests
import re
import time
from bs4 import BeautifulSoup
from _common import create_mobile_library_file

WEBSITE = 'https://www.suffolklibraries.co.uk/'
ROUTES = 'mobiles-home/mobile-route-schedules/'
BOUNDS = '0.34,51.9321,1.7689,52.5502'
NOM_URL = 'https://nominatim.openstreetmap.org/search?format=json&q='

## Example request https://nominatim.openstreetmap.org/search?q=The Drift, Coney Weston&viewport=0.34,51.9321,1.7689,52.5502


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
            if '2020' in para.text:
                dates = para.text.strip().split(', ')

        if len(dates) > 0:
            date = datetime.strptime(dates[2] + ' 2020', '%d %B %Y')
            start = date.strftime('%Y-%m-%d')
        else:
            start = ''

        # For each stop get the stop details
        for stop in stop_list_soup.find_all('tr')[1:]:

            route = mobile_library + ' ' + route_link['route']
            community = stop.find_all('td')[1].string.strip()
            stop_number = stop.find_all('td')[0].string.strip()
            if stop_number == '15B':
                stop_name = 'Brook Inn, Car Park'
            else: 
                stop_name = stop.find_all('td')[2].string.strip()
            address = stop_name + ', ' + community
            postcode = ''
            longitude = ''
            latitude = ''
            day = route_link['day'][:-1]
            times = re.sub(r'\D', '', stop.find_all('td')[3].text)
            arrival = times[:2] + ':' + times[2:4]
            departure = times[4:6] + ':' + times[6:]
            timetable = WEBSITE + route_link['href']

            # Geocoding: get the lat/lng
            #geo_json = requests.get(
            #    NOM_URL + address + '&viewbox=' + BOUNDS).json()

            #if len(geo_json) == 0:
            #    geo_json = requests.get(
            #        NOM_URL + community + '&viewbox=' + BOUNDS).json()

            #if len(geo_json) > 0:
            #    longitude = geo_json[0]['lon']
            #    latitude = geo_json[0]['lat']

            mobiles.append(
                [mobile_library, route, community, stop_name, address, postcode, longitude, latitude,
                 day, 'Public', arrival, departure, 'FREQ=WEEKLY;INTERVAL=4', start, '', '', timetable]
            )

            # time.sleep(10)

    create_mobile_library_file('Suffolk', 'suffolk.csv', mobiles)


run()
