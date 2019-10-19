import requests
import json
import csv

DATA_SOURCE = '../raw/milton_keynes.csv'
DATA_OUTPUT = '../data/milton_keynes.csv'

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
            postcode_request = requests.get('https://api.postcodes.io/postcodes/' + postcode)
            postcode_data = json.loads(postcode_request.text)
            latitude = postcode_data['result']['latitude']
            longitude = postcode_data['result']['longitude']

            mobiles.append(
                ['Mobile', day, community, stop_name, address, postcode, longitude, latitude,
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
                ['Milton Keynes', sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])

run()