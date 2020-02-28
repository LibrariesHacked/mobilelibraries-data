import xml.etree.ElementTree as ET
import csv
import re
from datetime import datetime
from _common import create_mobile_library_file

DATA_SOURCE = '../raw/midlothian.kml'


def run():

    ns = {'kml': 'http://www.opengis.net/kml/2.2'}

    dates = {
        1: {
            "Monday": "2020-02-24",
            "Tuesday": "2020-02-25",
            "Wednesday": "2020-02-26",
            "Thursday": "2020-02-27",
            "Friday": "2020-02-28"
        },
        2: {
            "Monday": "2020-03-02",
            "Tuesday": "2020-03-03",
            "Wednesday": "2020-03-04",
            "Thursday": "2020-03-05",
            "Friday": "2020-03-06"
        }
    }

    tree = ET.parse(DATA_SOURCE)
    root = tree.getroot()

    mobiles = []

    timetable = 'https://www.midlothian.gov.uk/info/427/libraries/446/mobile_library'

    mobile_library = 'Mobile'

    for route in root.find('kml:Document', ns).findall('kml:Folder', ns):

        frequency = 'FREQ=WEEKLY;INTERVAL=2'

        route_name = route.find('kml:name', ns).text.replace(' Stops', '')
        day = 'Monday'
        if 'Tuesday' in route_name:
            day = 'Tuesday'
        if 'Wednesday' in route_name:
            day = 'Wednesday'
        if 'Thursday' in route_name:
            day = 'Thursday'
        if 'Friday' in route_name:
            day = 'Friday'

        duplicate = False
        week = 2
        if 'Week 1' in route_name:
            week = 1
        if '&' in route_name:
            # stop is also a route 2 stop
            duplicate = True
            route_name = route_name.replace('Week 1 & 2', 'Week 1')
        start = dates[week][day]

        for stop in route.findall('kml:Placemark', ns):

            address = stop.find('kml:name', ns).text
            stop_name = stop.find('kml:name', ns).text
            community = stop.find('kml:name', ns).text

            description = stop.find('kml:description', ns).text.strip()

            times_result = re.search(
                r'(\d{1,2}:\d{2}).*?(\d{1,2}:\d{2})', description.replace('.', ':'))
            arrival = times_result.group(1)
            departure = times_result.group(2)

            coordinates = stop.find('kml:Point', ns).find(
                'kml:coordinates', ns).text.strip()
            longitude = coordinates.split(',')[0]
            latitude = coordinates.split(',')[1]

            mobiles.append(
                [mobile_library, route_name, community, stop_name, address, '', longitude, latitude,
                    day, 'Public', arrival, departure, frequency, start, '', '', timetable]
            )

            if duplicate:
                mobiles.append(
                    [mobile_library, route_name.replace('Week 1', 'Week 2'), community, stop_name, address, '', longitude, latitude,
                        day, 'Public', arrival, departure, frequency, dates[2][day], '', '', timetable]
                )

    create_mobile_library_file(
        'Midlothian', 'midlothian.csv', mobiles)


run()
