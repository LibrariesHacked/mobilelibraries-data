import csv
from _common import create_mobile_library_file

DATA_SOURCE = '../raw/birmingham.csv'


def run():

    timetable = 'https://www.birmingham.gov.uk/info/50163/library_services/1479/mobile_library_service/3'
    mobiles = []

    with open(DATA_SOURCE, 'r') as raw:
        reader = csv.reader(raw, delimiter=',', quotechar='"')
        for row in reader:

            day = row[0]
            arrival = row[1]
            departure = row[2]
            community = row[3]
            stop_name = row[4]
            latitude = row[5]
            longitude = row[6]
            frequency = row[7]
            start = row[8]
            route = row[9]
            address = stop_name + ', ' + community

            mobiles.append(
                ['Mobile', route, community, stop_name, address, '', longitude, latitude,
                    day, 'Public', arrival, departure, frequency, start, '', '', timetable]
            )

    create_mobile_library_file('Birmingham', 'birmingham.csv', mobiles)


run()
