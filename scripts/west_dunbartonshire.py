import json
import csv
import xml.etree.ElementTree as ET
from datetime import datetime
import re

# The original raw data for Wst Dunbartonshire is KML data
DATA_SOURCE = '../raw/west_dunbartonshire.kml'
DATA_OUTPUT = '../data/west_dunbartonshire.csv'


def run():

    dates = {
        "Monday": "2019-04-08",
        "Tuesday": "2019-04-09",
        "Wednesday": "2019-04-10",
        "Thursday": "2019-04-11",
        "Friday": "2019-04-12",
        "Saturday": "2019-04-13"
    }

    # add more as needed
    namespaces = {'xmlns': 'http://www.opengis.net/kml/2.2'}
    kml_tree = ET.parse(DATA_SOURCE)
    root = kml_tree.getroot()

    organisation = 'West Dunbartonshire'
    mobile = 'Mobile'
    timetable = 'https://www.west-dunbarton.gov.uk/libraries/mobile-housebound-services/mobile-library-service/mobile-library-timetable/'
    mobiles = []

    for folder in root.find('xmlns:Document', namespaces).findall('xmlns:Folder', namespaces):

        folder_name = folder.find('xmlns:name', namespaces).text
        sections = re.split('(?i)morning|afternoon', folder_name)

        route_name = sections[0].strip()
        community = sections[1].replace('-', '').strip()

        start = dates[route_name]

        for stop in folder.findall('xmlns:Placemark', namespaces):
            stop_name = stop.find('xmlns:name', namespaces).text
            address = stop_name + ', ' + community
            coords = stop.find('xmlns:Point', namespaces).find(
                'xmlns:coordinates', namespaces).text
            geox = coords.split(',')[0].strip()
            geoy = coords.split(',')[1].strip()
            day = route_name
            description = stop.find('xmlns:description', namespaces).text
            description_sections = re.split(
                '(?i)morning|afternoon', description)
            times = description_sections[1].strip().replace(
                '.', '').replace(':', '')
            times_matcher = re.compile('\d{1,4}')
            times_matches = re.findall(times_matcher, times)
            if len(times_matches) > 0:
                arrival = times_matches[0]
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

            if len(times_matches) > 1:
                departure = times_matches[1]
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

            mobiles.append(
                [mobile, route_name, community, stop_name, address, '', geox, geoy,
                 day, arrival, departure, 'FREQ=WEEKLY;INTERVAL=2', start, '', timetable]
            )

    with open(DATA_OUTPUT, 'w', encoding='utf8', newline='') as out_csv:
        mob_writer = csv.writer(out_csv, delimiter=',',
                                quotechar='"', quoting=csv.QUOTE_MINIMAL)
        mob_writer.writerow(
            ['organisation', 'mobile', 'route', 'community', 'stop', 'address', 'postcode', 'geox',
             'geoy', 'day', 'arrival', 'departure', 'frequency', 'start', 'end',  'timetable'])
        for sto in mobiles:
            mob_writer.writerow(
                [organisation, sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])


run()
