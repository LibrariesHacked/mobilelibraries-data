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

WEBSITE = 'https://www.suffolklibraries.co.uk'
ROUTES = '/mobiles-home/mobile-route-schedules/'
BOUNDS = '0.34,51.9321,1.7689,52.5502'
NOM_URL = 'https://nominatim.openstreetmap.org/search?format=json&countrycodes=gb&q='


def run():
    """Runs the main script"""

    # manual locations
    locations = {
        'Glendale, Culford': [52.295329, 0.693698],
        'Village Hall, Risby': [52.265824, 0.634437],
        'Tutelina Road, Great Welnetham': [52.205614, 0.750686],
        'Walnut Tree Cottage, West Stow': [52.334333, 0.521259],
        'The Green, Honington': [52.336852, 0.806826],
        'Bus Shelter, Boxstead Row': [52.139440, 0.677079],
        'Village Hall, Brockley': [52.159501, 0.667900],
        'Top of the Hill, Hartest': [52.135100, 0.687976],
        'Community Hall, Whepstead': [52.193932, 0.681194],
        'Three Ways, Whepstead': [52.194667, 0.673889],
        'Village Hall, Ousden': [52.204576, 0.553058],
        'Church, Ousden': [52.207750, 0.538848],
        'Chequers, Gazely': [52.247857, 0.517684],
        'Needham Hall, Needham Street': [52.263197, 0.520293],
        'The School, Tuddenham St Mary': [52.313586, 0.547267],
        'Opp. 14 Cavenham Road, Tuddenham St Mary': [52.312273, 0.550346],
        'Bishopscroft, Barningham': [52.356090, 0.890150],
        'Honey Pot Lane, Wattisfield': [52.320952, 0.951440],
        'Village Hall, Wattisfield': [52.330484, 0.948689],
        '109 Bury Road, Great Thurlow': [52.126156, 0.456243],
        'Meadow Drive, Horringer': [52.222825, 0.673222],
        'Church, Cotton': [52.261369, 1.032773],
        'Methodist Church, Cotton': [52.264101, 1.019484],
        'Village Hall, Norton': [52.257070, 0.866380],
        'Church Road, Newton Green': [52.036365, 0.796942],
        'Flint Cottages, Smallbridge': [52.173870, 0.794328],
        'Half Moon, Hepworth': [52.335184, 0.913022],
        'Ivy Nook, Beck Street, Hepworth': [52.346656, 0.920684],
        'Stanton Stores, Stanton': [52.323876, 0.884184],
        'Hilltop, Stanton': [52.333412, 0.880192],
        'Community Centre, Walsham Le Willows': [52.302602, 0.935680],
        'Town House Road, Walsham Le Willows': [52.300731, 0.943665],
        'Pumping Station, Cavendish': [52.090559, 0.640543],
        'Church, Cavendish': [52.087629, 0.632805],
        'The Chapel, Lawshall': [52.154713, 0.733109],
        'Swanfields, Lawshall': [52.155029, 0.727303],
        'Village Hall, Lawshall': [52.159793, 0.714417],
        'Village Hall, Buxhall': [52.180829, 0.915938],
        'Green Farm Cottage, Thorpe Morieux': [52.145783, 0.836211],
        'Village Hall, Thorpe Morieux': [52.148876, 0.837022],
        'Primary School, Boxford': [52.027547, 0.859810],
        'Bridge Farm Day Nursery, Martlesham': [52.081405, 1.288248],
        'Falcon Mobile Home Park, Martlesham': [52.064742, 1.281813],
        'Douglas Bader, Martlesham Heath': [52.060970, 1.272164],
        'Village Hall, Bentley': [51.989546, 1.071395],
        'Whissels Farm, Creeting St Mary': [52.177112, 1.085009],
        'Village Hall, Creeting St Mary': [52.172051, 1.070963],
        'Church, Little Stonham': [52.199084, 1.089106],
        'Magpie Inn, Little Stonham': [52.201534, 1.099858],
        'The Green, Higham': [52.260693, 0.557358],
        'Fenn View, Washbrook': [52.034945, 1.078822],
        'Church, Battisford': [52.149227, 1.001806],
        'Battisford Pre School, Battisford': [52.146993, 0.980069],
        'Farnish House, Botesdale': [52.341407, 1.006361],
        'Village Hall, Botesdale': [52.345144, 1.008976],
        'Backhills, Botesdale': [52.345331, 1.006312],
        'Broom Knoll, East Bergholt': [51.971927, 1.061666],
        'South View, East Bergholt': [51.976061, 1.055943],
        'Red Lion, East Bergholt': [51.971688, 1.011434],
        'Paddock Way, Bildeston': [52.105056, 0.910917],
        'White Horse, Hitcham': [52.124151, 0.894430],
        'Village Hall, Hitcham': [52.127769, 0.900729],
        'The Swan car park, Hoxne': [52.349545, 1.199516],
        'St Edmunds House, Hoxne': [52.339660, 1.208437],
        'Fish and Chip shop, Mendlesham': [52.251120, 1.082581],
        'Recreation ground, Mendlesham': [52.248412, 1.078985],
        'The Green, Mendlesham': [52.226707, 1.069991],
        'Lay-by, Wickham Skeith': [52.281808, 1.071562],
        'Swan House, Wickham Skeith': [52.286511, 1.064710],
        'Moorlands, Hollesley': [52.054773, 1.430125],
        'Shepherd & Dog PH, Hollesley': [52.050942, 1.430870],
        'Harewood House, Hollesley': [52.039702, 1.412796],
        'Orchardleigh, North Cove': [52.446345, 1.629062],
        'Old Post Office, Mutford': [52.437027, 1.650539],
        'Hartismere House, Laxfield': [52.300566, 1.363823],
        'New Dawn, Chediston': [52.354000, 1.450951],
        'Midsummer Cottage, Chediston': [52.348039, 1.459990],
        'Nursery, Rendlesham': [52.126116, 1.414609],
        'Village Hall, Wenhaston': [52.323520, 1.558421],
        'Ashburnham Way (Co-op car park), Carlton Colville': [52.457034, 1.703553],
        'Green, Saxtead': [52.231834, 1.299388],
        'Foxearth Nursing Home, Saxtead': [52.247412, 1.297638],
        'Bell Inn, Middleton': [52.255023, 1.557760],
        'Mulberry Bush nursery, Eye': [52.329782, 1.144394],
        'Hartismere House, Eye': [52.322536, 1.139949],
        'Spring Park, Otley': [52.157872, 1.229017],
        'Village Stores, Otley': [52.151381, 1.220365],
        'Village Hall, Snape': [52.170943, 1.500930],
        'Near pond, Lound': [52.547929, 1.682302],
        'Lound Hall, Lound': [52.530358, 1.702772]
    }

    mobiles = []
    coordinates = []

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

            if address not in locations:
                # Geocoding: get the lat/lng
                geo_json = requests.get(
                    NOM_URL + address + '&viewbox=' + BOUNDS).json()

                if len(geo_json) == 0:
                    geo_json = requests.get(
                        NOM_URL + community + '&viewbox=' + BOUNDS).json()

                if len(geo_json) > 0:
                    x = round(float(geo_json[0]['lon']), 5)
                    y = round(float(geo_json[0]['lat']), 5)
                    bbox = BOUNDS.split(',')
                    if float(bbox[0]) <= x and x <= float(bbox[2]) and float(bbox[1]) <= y and y <= float(bbox[3]) and x not in coordinates:
                        # Don't add duplicates - we'll manually sort em out laters
                        coordinates.append(x)
                        longitude = x
                        latitude = y
            else:
                longitude = locations[address][1]
                latitude = locations[address][0]

            mobiles.append(
                [mobile_library, route, community, stop_name, address, postcode, longitude, latitude,
                 day, 'Public', arrival, departure, 'FREQ=WEEKLY;INTERVAL=4', start, '', '', timetable]
            )

            time.sleep(6)

    create_mobile_library_file('Suffolk', 'suffolk.csv', mobiles)


run()
