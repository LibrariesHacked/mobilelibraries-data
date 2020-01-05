import requests
import json
import csv
from _common import create_mobile_library_file

DATA_SOURCE = '../raw/somerset.csv'


def run():

    timetable = 'https://www.somerset.gov.uk/libraries-leisure-and-communities/libraries/library-facilities/mobile-library/'
    mobiles = []

    with open(DATA_SOURCE, 'r') as som_raw:
        mobreader = csv.reader(som_raw, delimiter=',', quotechar='"')
        next(mobreader, None)  # skip the headers
        for row in mobreader:

            mobile_library = 'Mobile'
            frequency = 'FREQ=WEEKLY;INTERVAL=4'
            route = row[0].strip()
            community = row[1].strip()
            stop_name = row[2].strip()
            address = stop_name + ', ' + community
            postcode = row[3].strip()
            arrival = row[4].strip().replace('.', ':')
            departure = row[5].strip().replace('.', ':')
            day = row[6].strip()
            start = row[7].strip()

            postcode_request = requests.get(url)
            postcode_data = json.loads(postcode_request.text)
            latitude = postcode_data['result']['latitude']
            longitude = postcode_data['result']['longitude']

            mobiles.append(
                [mobile_library, route, community, stop_name, address, postcode, longitude, latitude,
                    day, 'Public', arrival, departure, frequency, start, '', '', timetable]
            )

    create_mobile_library_file('Somerset', 'somerset.csv', mobiles)


run()
