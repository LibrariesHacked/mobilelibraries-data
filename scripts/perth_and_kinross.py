import xml.etree.ElementTree as ET
import csv

DATA_SOURCE = '../raw/perth_and_kinross.kml'
DATA_OUTPUT = '../data/angus.csv'

def run():

    ns = {'kml': 'http://www.opengis.net/kml/2.2'}

    tree = ET.parse(DATA_SOURCE)
    root = tree.getroot()

    mobiles = []
    timetable = 'https://www.culturepk.org.uk/libraries/services-in-the-community/mobile-library-service/'

    for stop in root.find('kml:Document', ns).find('kml:Folder', ns).findall('kml:Placemark', ns):

        stop_name = stop.find('kml:name', ns).text

        mobiles.append(
            [mobile_library, route, community, stop_name, address, '', longitude, latitude,
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
                ['Angus', sto[0], sto[1], sto[2], sto[3], sto[4], sto[5],
                 sto[6], sto[7], sto[8], sto[9], sto[10], sto[11], sto[12], sto[13], sto[14]])

run()
