import requests
import json
import csv

DATA_SOURCE = '../raw/portsmouth.csv'
DATA_OUTPUT = '../data/portsmouth.csv'

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
                ['Portsmouth', sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])

run()
