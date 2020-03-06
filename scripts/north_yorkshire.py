import csv
from _common import create_mobile_library_file

DATA_SOURCE = '../raw/north_yorkshire.csv'

def run():

    timetable = 'https://www.northyorks.gov.uk/supermobile-library'
    mobiles = []

    with open(DATA_SOURCE, 'r') as raw:
        reader = csv.reader(raw, delimiter=',', quotechar='"')
        next(reader, None)  # skip the headers
        for row in reader:

            day = row[0]
            arrival = row[3]
            departure = row[4]
            community = row[1]
            stop_name = row[2]
            postcode = ''
            start = row[5]
            address = stop_name + ', ' + community
            frequency = 'FREQ=WEEKLY;INTERVAL=2'
            latitude = row[6]
            longitude = row[7]

            mobiles.append(
                ['Supermobile', day, community, stop_name, address, postcode, longitude, latitude,
                    day, 'Public', arrival, departure, frequency, start, '', '', timetable]
            )

    create_mobile_library_file('North Yorkshire', 'north_yorkshire.csv', mobiles)


run()
