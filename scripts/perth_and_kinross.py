import xml.etree.ElementTree as ET
import csv
import re
from datetime import datetime

DATA_SOURCE = '../raw/perth_and_kinross.kml'
DATA_OUTPUT = '../data/perth_and_kinross.csv'

def run():

    ns = {'kml': 'http://www.opengis.net/kml/2.2'}

    tree = ET.parse(DATA_SOURCE)
    root = tree.getroot()

    mobiles = []
    frequency = 'FREQ=WEEKLY;INTERVAL=2'
    timetable = 'https://www.culturepk.org.uk/libraries/services-in-the-community/mobile-library-service/'

    for mobile in root.find('kml:Document', ns).findall('kml:Folder', ns):

        mobile_library = mobile.find('kml:name', ns).text
        for stop in mobile.findall('kml:Placemark', ns):

            address = stop.find('kml:name', ns).text
            places = address.split(' - ')
            stop_name = places[0]
            community = places[-1]
            
            description = stop.find('kml:description', ns).text.strip()

            description_parts = description.split('<br>')

            times = description_parts[0]
            times_result = re.search(r'(\d{2}:\d{2}).*(\d{2}:\d{2})', times)
            arrival = times_result.group(1)
            departure = times_result.group(2)
            route = description_parts[1]
            for part in description_parts:
                if '-Mar' in part:
                    date = datetime.strptime(part.split(',')[1].strip() + ' 2019', '%d-%b %Y')
            start = date.strftime('%Y-%m-%d')
            day = date.strftime('%A')

            coordinates = stop.find('kml:Point', ns).find('kml:coordinates', ns).text.strip()
            longitude = coordinates.split(',')[0]
            latitude = coordinates.split(',')[1]

            mobiles.append(
                [mobile_library, route, community, stop_name, address, '', longitude, latitude,
                    day, arrival, departure, frequency, start, '', timetable]
            )

    with open(DATA_OUTPUT, 'w', encoding='utf8', newline='') as out_csv:
        mob_writer = csv.writer(out_csv, delimiter=',',
                                quotechar='"', quoting=csv.QUOTE_MINIMAL)
        mob_writer.writerow(
            ['organisation', 'mobile', 'route', 'community', 'stop', 'address', 'postcode', 'geox',
             'geoy', 'day', 'arrival', 'departure', 'frequency', 'start', 'end',  'timetable'])
        for sto in mobiles:
            mob_writer.writerow(
                ['Perth and Kinross', sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])

run()
