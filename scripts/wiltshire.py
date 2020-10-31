"""Web scrapes Wiltshire Mobile Library Timetables and geocodes them """

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

BOUNDS = '-2.3656,50.945,-1.4857,51.7031'
NOM_URL = 'https://nominatim.openstreetmap.org/search?format=json&countrycodes=gb&q='
DATA_OUTPUT_RAW = '../raw/wiltshire.csv'

# manual locations
locations = {}


def run():
  """Runs the main script"""

  # Scrape stop information. This is a single web page listing stops
  stop_list = 'https://services.wiltshire.gov.uk/MobileLibrary/Library/StopList'
  stop_list_html = requests.get(stop_list)
  stop_list_soup = BeautifulSoup(stop_list_html.text, 'html.parser')

  # If we don't already have it, create the raw file
  if not os.path.isfile(DATA_OUTPUT_RAW):
    mobiles = []
    # For each stop get the stop details
    for link in stop_list_soup.find_all('a'):
        # Detect whether the link is a link to a stop
        if '/MobileLibrary/Library/Stop/' in link.get('href'):

          # Get the webpage
          stop_url = 'https://services.wiltshire.gov.uk' + link.get('href')
          stop_html = requests.get(stop_url)
          stop_soup = BeautifulSoup(stop_html.text, 'html.parser')

          # General stop information
          stop_name = stop_soup.find('h2').text
          community = stop_name.split(', ')[0]
          stop_name = stop_name.split(
              ', ')[1].replace(' (fortnightly stop)', '')
          address = stop_name + ', ' + community

          # There are some stops that are two weekly but they're part of separate routes.  Keep them separate
          frequency = 4

          # Detailed information for the stop is found in the table.
          table = stop_soup.find('table').find('tbody')
          stop_rows = table.find_all('tr')

          for stop in stop_rows:
            round_name = stop.find('a').text.replace(
                '\r\n', '').replace(' (fortnightly stop)', '')
            mobile_library = round_name.split(
                ', ')[0].replace(' mobile library', '')
            day_week = round_name.split(', ')[1]
            route = day_week.replace('week', 'Week')
            week = day_week.split(' week ')[1]
            day = day_week.split(' week ')[0]
            date = datetime.strptime(stop.find('li').text, '%A %d %B, %Y')
            date_output = date.strftime('%Y-%m-%d')

            start = stop.find_all('td')[1].text
            end = stop.find_all('td')[2].text
            timetable = 'http://services.wiltshire.gov.uk' + \
                stop.find('a').get('href')

            # Mobile,Route,Stop,Community,Address,Longitude,Latitude,Date,Day,Frequency,Start,End,Timetable
            mobile = {'mobile': mobile_library, 'route': route, 'stop': stop_name, 'community': community, 'address': address,
                      'date': date_output, 'day': day, 'frequency': frequency, 'start': start, 'end': end, 'timetable': timetable}
            mobiles.append(mobile)
            time.sleep(1)

    with open(DATA_OUTPUT_RAW, 'w', encoding='utf8', newline='') as out_raw:
      mob_writer = csv.writer(
          out_raw, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
      mob_writer.writerow(['Mobile', 'Route', 'Community', 'Stop', 'Address',
                           'Date', 'Day', 'Frequency', 'Start', 'End', 'Timetable'])

      for sto in mobiles:
        mob_writer.writerow([sto['mobile'], sto['route'], sto['community'], sto['stop'], sto['address'],
                             sto['date'], sto['day'], sto['frequency'], sto['start'], sto['end'], sto['timetable']])

  mobiles = []
  coordinates = []
  with open(DATA_OUTPUT_RAW, 'r', encoding='utf8', newline='') as raw:
    mobreader = csv.reader(raw, delimiter=',', quotechar='"')
    next(mobreader, None)  # skip the headers
    # Mobile,Route,Community,Stop,Address,Date,Day,Frequency,Start,End,Timetable
    for row in mobreader:

      longitude = ''
      latitude = ''

      if row[4] not in locations:
        # Geocoding: get the lat/lng
        geo_json = requests.get(NOM_URL + row[4] + '&viewbox=' + BOUNDS).json()

        if len(geo_json) == 0:
          geo_json = requests.get(
              NOM_URL + row[2] + '&viewbox=' + BOUNDS).json()

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
        longitude = locations[row[4]][1]
        latitude = locations[row[4]][0]

      # Mobile,Route,Stop,Community,Address,Longitude,Latitude,Date,Day,Frequency,Start,End,Timetable
      mobile = [row[0], row[1], row[2], row[3], row[4], '', longitude,
                latitude, row[6], 'Public', row[8], row[9], 'FREQ=WEEKLY;INTERVAL=4', row[5], '', '', row[10]]
      mobiles.append(mobile)

  create_mobile_library_file('Wiltshire', 'wiltshire.csv', mobiles)


run()
