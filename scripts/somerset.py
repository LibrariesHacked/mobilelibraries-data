import requests
import json
import csv

DATA_SOURCE = '../raw/somerset.csv'
DATA_OUTPUT = '../data/somerset.csv'

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

            url = 'https://api.postcodes.io/postcodes/' + postcode
            postcode_request = requests.get('https://api.postcodes.io/postcodes/' + postcode)
            postcode_data = json.loads(postcode_request.text)
            latitude = postcode_data['result']['latitude']
            longitude = postcode_data['result']['longitude']

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
                ['Somerset', sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])

run()
