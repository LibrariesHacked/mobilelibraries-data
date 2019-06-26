import csv
import collections
import requests
import pandas as pd
import geopandas
import json
import time
from shapely.geometry import Point
from shapely.geometry import LineString

API_KEY = '5b3ce3597851110001cf624860a035e0c0bf48c690561cefd3ff4769'
STOP_DATA = '../data/west_dunbartonshire.csv'
OUTPUT_DATA = '../data/west_dunbartonshire_routes.geojson'


def run():
    """Runs the main script"""

    routes = {}
    geodata = []
    with open(STOP_DATA, 'rt') as mobile_csv:

        reader = csv.reader(mobile_csv, delimiter=',', quotechar='"')
        next(reader, None)  # skip the headers
        # make sure the rows are sorted by mobile, route, and arrival time
        sorted_rows = sorted(reader, key=lambda row: (row[1], row[2], row[10]))

        for (idx, row) in enumerate(sorted_rows):

            mobile = str(row[1])
            route = str(row[2])
            stop = str(row[4]),
            stop = stop[0]
            longitude = float(row[7])
            latitude = float(row[8])

            # Add to object
            if route not in routes:
                # Create an ordered dictionary so we keep track of stop order
                routes[route] = collections.OrderedDict()

            routes[route][idx] = {
                'longitude': str(longitude),
                'latitude': str(latitude),
                'mobile': str(mobile),
                'stop': str(stop)
            }

    for route in routes:

        trip_lookup = []
        trip_stops = {
        }

        # construct the URL from the stops
        url = 'https://api.openrouteservice.org/directions?format=geojson&api_key=' + \
            API_KEY + '&profile=driving-hgv&preference=fastest&coordinates='
        for (tr, idx) in enumerate(routes[route]):

            route_stop = routes[route][idx]
            url = url + route_stop['longitude'] + \
                ',' + route_stop['latitude'] + '|'

            # Keep track of our trips for later
            if 'origin_stop' in trip_stops and 'destination_stop' not in trip_stops:
                trip_stops['destination_stop'] = route_stop['stop']
                trip_stops['destination_stop_longitude'] = route_stop['longitude']
                trip_stops['destination_stop_latitude'] = route_stop['latitude']
            if 'origin_stop' not in trip_stops:
                trip_stops['origin_stop'] = route_stop['stop']
                trip_stops['origin_stop_longitude'] = route_stop['longitude']
                trip_stops['origin_stop_latitude'] = route_stop['latitude']
            if 'origin_stop' in trip_stops and 'destination_stop' in trip_stops:
                trip_lookup.append({
                    'origin_stop': trip_stops['origin_stop'],
                    'origin_stop_longitude': trip_stops['origin_stop_longitude'],
                    'origin_stop_latitude': trip_stops['origin_stop_latitude'],
                    'destination_stop': trip_stops['destination_stop'],
                    'destination_stop_longitude': trip_stops['destination_stop_longitude'],
                    'destination_stop_latitude': trip_stops['destination_stop_latitude']
                })
                trip_stops['origin_stop'] = route_stop['stop']
                trip_stops['origin_stop_longitude'] = route_stop['longitude']
                trip_stops['origin_stop_latitude'] = route_stop['latitude']
                del trip_stops['destination_stop']
                del trip_stops['destination_stop_longitude']
                del trip_stops['destination_stop_latitude']

        # Only continue if there is more than one stop
        if len(routes[route]) > 1:
            res_data = requests.get(url[:-1]).json()

            if 'error' not in res_data:

                # In the properties are the indexes of the waypoints
                waypoints = res_data['features'][0]['properties']['way_points']
                segments = res_data['features'][0]['properties']['segments']

                # We need to create an array of origin/destination index
                trips = []
                origin = None
                destination = None
                for stop in waypoints:
                    if origin is None:
                        origin = stop
                    elif destination is None:
                        destination = stop
                        trips.append([origin, destination])
                        origin = stop
                        destination = None

                for trip_idx, trip_item in enumerate(trips):

                    line = LineString(
                        res_data['features'][0]['geometry']['coordinates'][trip_item[0]:trip_item[1] + 1])

                    route_list = [val for key, val in routes[route].items()]
                    geodata.append(
                        {
                            'route': route,
                            'mobile': route_list[0]['mobile'],
                            'origin_stop': trip_lookup[trip_idx]['origin_stop'],
                            'origin_stop_longitude': trip_lookup[trip_idx]['origin_stop_longitude'],
                            'origin_stop_latitude': trip_lookup[trip_idx]['origin_stop_latitude'],
                            'destination_stop': trip_lookup[trip_idx]['destination_stop'],
                            'destination_stop_longitude': trip_lookup[trip_idx]['destination_stop_longitude'],
                            'destination_stop_latitude': trip_lookup[trip_idx]['destination_stop_latitude'],
                            'distance': segments[trip_idx]['distance'],
                            'duration': segments[trip_idx]['duration'],
                            'geo': line
                        })

            time.sleep(6)

    frame = pd.DataFrame(data=geodata)
    geodf = geopandas.GeoDataFrame(
        frame, crs={'init': 'epsg:4326'}, geometry='geo')

    # output route as geojson format file
    geodf.to_file(OUTPUT_DATA, driver="GeoJSON")


run()
