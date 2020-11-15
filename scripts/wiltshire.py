"""Web scrapes Wiltshire Mobile Library Timetables and geocodes them """
# coding: utf8

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
locations = {
  'Aldhelm Court, Bradford on Avon': [51.339966, -2.240846],
  'Wiltshire Heights, Bradford on Avon': [51.353336, -2.250670],
  'Cedar Court, Bradford on Avon': [51.353286, -2.249308],
  'Near School, Lea': [51.581558, -2.055383],
  'Trowbridge Oaks, Trowbridge': [51.316750, -2.194076],
  'Old Vicarage, Trowbridge': [51.342102, -2.204041],
  'Wingfield Lodge and Memory Lane, Trowbridge': [51.316671, -2.223650],
  'Florence Court, Trowbridge': [51.311834, -2.212262],
  'Village Hall, All Cannings': [51.355789, -1.898759],
  'Thornbank, Melksham': [51.370161, -2.139439],
  'Kestrel Court, Melksham': [51.357684, -2.128035],
  'Brookside, Melksham': [51.373666, -2.133531],
  'The Warren, Savernake': [51.38639832,-1.64673640],
  'Village Hall, Ashton Keynes': [51.644664, -1.934588],
  'Telephone Box, Boscombe/Allington': [51.151691, -1.708727],
  'Little Foxes, Brinkworth': [51.563849, -1.954993],
  'Village Hall, Brinkworth': [51.558930, -1.980391],
  'Bus Turning Area, East Gomeldon': [51.119785, -1.734351],
  'The School, Newton Tony': [51.161370, -1.690837],
  'Bendy Bow, Oaksey': [51.640163, -2.021539],
  'Malvern Way, Porton': [51.130972, -1.734251],
  'Westbury Court, Westbury': [51.261424, -2.187596],
  'Glebe Hall, Winterbourne Earls': [51.108893, -1.751219],
  'Earls Manor Court, Winterbourne Earls': [51.108631, -1.753777],
  'Village Hall, Great Bedwyn': [51.379270, -1.597272],
  'Sudweeks Court, Devizes': [51.354153, -1.996168],
  'Needham House , Devizes': [51.354091, -1.988184],
  'Holly Lodge, Pewsey': [51.344706, -1.777394],
  'Limberstone, Beechingstoke': [51.331357, -1.878275],
  'Fairways, Chippenham': [51.479627, -2.129945],
  'The Street, Chirton': [51.315385, -1.895192],
  'Naish House Farm, Spirthill': [51.478595, -2.008050],
  'Social Club Car Park, Woodborough': [51.337744, -1.848242],
  'Burford Road, East Harnham': [51.057469, -1.790554],
  'Ramleaze Drive, Fugglestone Red': [51.090737, -1.827596],
  'Berkshire Road, West Harnham': [51.062576, -1.813221],
  'Village Hall, Alderbury': [51.039737, -1.727965],
  'Pavilion, Bishopdown Farm': [51.088790, -1.783824],
  'Ashmore Close, Whiteparish': [51.013699, -1.649020],
  'Near old School, Littleton Drew': [51.518577, -2.205357],
  'Pitts Croft, Neston': [51.414241, -2.201008],
  'The Green, Nomansland': [50.955040, -1.640480],
  'Westwood Road, Rudloe': [51.428861, -2.221269],
  'High Street, Sherston': [51.571011, -2.213584],
  'Vale View Road, South Newton': [51.111386, -1.876435],
  'Opposite Post Office, Woodfalls': [50.981046, -1.718624],
  'Village Hall, Kington Langley': [51.491076, -2.108454],
  'Beech Grange, Landford': [50.969088, -1.633596],
  'Napier Crescent, Laverstock': [51.072473, -1.775599],
  'Elm Close, Laverstock': [51.080190, -1.773027],
  'King’s Lodge School, Pewsham': [51.447245, -2.101087],
  'Near Green, Lower Stanton': [51.518132, -2.137172],
  'The Homestead, Trowbridge': [51.311546, -2.209989],
  'Grove Court, Trowbridge': [51.309340, -2.213692],
  'Manor Court , Trowbridge': [51.310351, -2.225383],
  'Romney House, Trowbridge': [51.324740, -2.231021],
  'Teazle Court, Trowbridge': [51.321277, -2.195197],
  'The Village Hall, Bower Chalke': [51.007099, -1.974663],
  'Marlborough Lodge, Marlborough': [51.419680, -1.716561],
  'St. Luke’s Court, Marlborough': [51.425336, -1.735820],
  'The Poplars Inn, Wingfield': [51.309879, -2.257550],
  'School, Winsley': [51.349689, -2.284468],
  'Marden Court, Calne': [51.438350, -2.007662],
  'Bank House High Street, Hindon': [51.095477, -2.130386],
  'The Green, Urchfont': [51.350208, -1.989434],
  '43 Zeals Rise, Zeals': [51.083954, -2.317970],
  'The Cedars, Purton': [51.587421, -1.872733],
  'Dairy View, Wootton Bassett': [51.535281, -1.898116],
  'York Place, Marlborough': [51.422884, -1.727068],
  'Castle Court, Marlborough': [51.417016, -1.732510],
  'Churchill Court, Marlborough': [51.420287, -1.724802],
  'Purcells Court, Marlborough': [51.418241, -1.727213],
  'Bybrook House, Box': [51.419479, -2.269168],
  'Holton House, Corsham': [51.432679, -2.185968],
  'Jargeau Court, Corsham': [51.429260, -2.187539],
  'Village Hall, Winterslow': [51.093771, -1.655713],
  'St. Clements, Chippenham': [51.461467, -2.131395],
  'Croft Court, Chippenham': [51.450997, -2.138441],
  'The Priory, Chippenham': [51.465763, -2.117262],
  'Seymour House, Chippenham': [51.458630, -2.106781],
  'Ferfoot, Chippenham': [51.466389, -2.136529],
  'Lansdowne Hall, Derry Hill': [51.437767, -2.056734],
  'Seymour Arms Pub, East Knoyle': [51.070786, -2.170937],
  'Village hall, Horningsham': [51.173148, -2.270324], 
  'School, Kington St Michael': [51.496798, -2.143535], 
  'Post Office, Kington St Michael': [51.494027, -2.139231], 
  'Robert Stokes Almshouse, Salisbury': [51.063322, -1.793977], 
  'St. Nicholas, Salisbury': [51.061495, -1.796328], 
  'Brympton House , Salisbury': [51.059167, -1.804453], 
  'Car Park, Larkhill': [51.198545, -1.814908], 
  'Tower House, Salisbury': [51.072817, -1.786985], 
  'Village Hall, Semington': [51.344664, -2.147945], 
  'By Market Cross, Castle Combe': [51.493552, -2.228876], 
  'Near School, Colerne': [51.441170, -2.261820], 
  'The Wheatsheaf, Lower Woodford': [51.114532, -1.822654], 
  'Long Leaze, Nettleton': [51.501181, -2.260505], 
  'Gloucester House, Salisbury': [51.083015, -1.803945], 
  'St. Mark''s House, Salisbury': [51.075724, -1.786107], 
  'Avonbourne Centre, Sarum': [51.099577, -1.789974], 
  'Hindes Meadow, Shrewton': [51.199727, -1.901414], 
  'Maddington Church Rooms, Shrewton': [51.194221, -1.905588], 
  'Castle Keep, Stratford-sub-Castle': [51.085225, -1.809127], 
  'The Green, Upper Wraxall': [51.468672, -2.284911], 
  'Bus stop, Ashton Common': [51.322769, -2.149756],
  'School, Chapmanslade': [51.229372, -2.251227],
  'The Elms, Holt': [51.357116, -2.199859],
  'Laverstock Care Centre, Salisbury': [51.085704, -1.775490],
  'Hardy House, Salisbury': [51.068875, -1.803861],
  'Longs Arms pub, Steeple Ashton': [51.310428, -2.135223]
}


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
