import requests
import json
import csv
from _common import create_mobile_library_file

DATA_SOURCE = '../raw/portsmouth.csv'


def run():

    timetable = 'https://www.portsmouth.gov.uk/ext/libraries/mobile-library'
    mobiles = []

    with open(DATA_SOURCE, 'r') as port_raw:
        mobreader = csv.reader(port_raw, delimiter=',', quotechar='"')
        next(mobreader, None)  # skip the headers
        for row in mobreader:

            mobile_library = 'Mobile'
            frequency = 'FREQ=WEEKLY;INTERVAL=1'
            route = row[0].strip()
            community = row[4].strip()
            stop_name = row[3].strip()
            address = stop_name + ', ' + community
            postcode = ''
            arrival = row[1].strip()
            departure = row[2].strip()
            day = row[0].strip()
            start = row[7].strip()
            latitude = row[5].strip()
            longitude = row[6].strip()

            mobiles.append(
                [mobile_library, route, community, stop_name, address, postcode, longitude, latitude,
                    day, 'Public', arrival, departure, frequency, start, '', '', timetable]
            )

    create_mobile_library_file('Portsmouth', 'portsmouth.csv', mobiles)


run()
