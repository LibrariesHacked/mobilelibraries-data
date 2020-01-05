import requests
import json
import csv
from _common import create_mobile_library_file

DATA_SOURCE = '../raw/milton_keynes.csv'


def run():

    timetable = 'https://www.milton-keynes.gov.uk/libraries/about-libraries/mobile-library-service'
    mobiles = []

    with open(DATA_SOURCE, 'r') as mk_raw:
        mobreader = csv.reader(mk_raw, delimiter=',', quotechar='"')
        next(mobreader, None)  # skip the headers
        for row in mobreader:

            day = row[0]
            arrival = row[1]
            departure = row[2]
            community = row[3]
            stop_name = row[4]
            postcode = row[5]
            start = row[6]
            address = stop_name + ', ' + community
            frequency = 'FREQ=WEEKLY;INTERVAL=1'

            url = 'https://api.postcodes.io/postcodes/' + postcode
            postcode_request = requests.get(url)
            postcode_data = json.loads(postcode_request.text)
            latitude = postcode_data['result']['latitude']
            longitude = postcode_data['result']['longitude']

            mobiles.append(
                ['Mobile', day, community, stop_name, address, postcode, longitude, latitude,
                    day, 'Public', arrival, departure, frequency, start, '', '', timetable]
            )

    create_mobile_library_file('Milton Keynes', 'milton_keynes.csv', mobiles)


run()
