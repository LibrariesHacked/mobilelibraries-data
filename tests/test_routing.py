import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import routing
from scripts import validate


class GenerateRoutesTests(unittest.TestCase):
    def test_canonical_mobile_name_is_preserved_in_route_and_trip_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            routes_dir = data_dir / "routes"
            data_dir.mkdir()
            stop_file = data_dir / "sample.csv"
            with stop_file.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=["mobile_name", "route", "stop", "geox", "geoy", "arrival"],
                )
                writer.writeheader()
                writer.writerows([
                    {"mobile_name": "Book Bus", "route": "Route A", "stop": "First", "geox": "-2.0", "geoy": "56.0", "arrival": "09:00"},
                    {"mobile_name": "Book Bus", "route": "Route A", "stop": "Second", "geox": "-2.1", "geoy": "56.1", "arrival": "10:00"},
                ])

            route_response = {
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[-2.0, 56.0], [-2.1, 56.1]]},
                    "properties": {"way_points": [0, 1], "segments": [{"distance": 100, "duration": 30}]},
                }]
            }
            with (
                patch.object(routing, "DATA_DIR", data_dir),
                patch.object(routing, "ROUTES_DIR", routes_dir),
                patch.object(routing, "OFFICIAL_ROUTES_DIR", routes_dir / "official"),
                patch.object(routing, "route_osrm", return_value=route_response),
                patch.object(routing.time, "sleep"),
            ):
                self.assertTrue(routing.generate_routes_for_authority("sample", engine="osrm"))

            with (routes_dir / "sample_routes.csv").open(encoding="utf-8", newline="") as file:
                trips = list(csv.DictReader(file))
            with (routes_dir / "sample_routes.geojson").open(encoding="utf-8") as file:
                features = json.load(file)["features"]

            self.assertEqual(["Book Bus"], [trip["mobile"] for trip in trips])
            self.assertEqual(["Book Bus"], [feature["properties"]["mobile"] for feature in features])


class RouteTripValidationTests(unittest.TestCase):
    def test_route_trip_relationships_match_stops(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            routes_dir = data_dir / "routes"
            routes_dir.mkdir()
            with (data_dir / "sample.csv").open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=["mobile_name", "route", "stop", "geox", "geoy"])
                writer.writeheader()
                writer.writerows([
                    {"mobile_name": "Book Bus", "route": "Route A", "stop": "First", "geox": "-2.00000", "geoy": "56.00000"},
                    {"mobile_name": "Book Bus", "route": "Route A", "stop": "Second", "geox": "-2.10000", "geoy": "56.10000"},
                ])
            with (routes_dir / "sample_routes.csv").open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=["mobile", "route", "origin_stop", "origin_stop_latitude", "origin_stop_longitude", "destination_stop", "destination_stop_latitude", "destination_stop_longitude"],
                )
                writer.writeheader()
                writer.writerow({
                    "mobile": "Book Bus",
                    "route": "Route A",
                    "origin_stop": "First",
                    "origin_stop_latitude": "56.00000",
                    "origin_stop_longitude": "-2.00000",
                    "destination_stop": "Second",
                    "destination_stop_latitude": "56.10000",
                    "destination_stop_longitude": "-2.10000",
                })

            self.assertEqual([], validate.validate_route_trip_files(data_dir))

    def test_reports_unknown_route_and_stop_location(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            routes_dir = data_dir / "routes"
            routes_dir.mkdir()
            with (data_dir / "sample.csv").open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=["mobile_name", "route", "stop", "geox", "geoy"])
                writer.writeheader()
                writer.writerow({"mobile_name": "Book Bus", "route": "Route A", "stop": "Known", "geox": "-2.00000", "geoy": "56.00000"})
            with (routes_dir / "sample_routes.csv").open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=["mobile", "route", "origin_stop", "origin_stop_latitude", "origin_stop_longitude", "destination_stop", "destination_stop_latitude", "destination_stop_longitude"])
                writer.writeheader()
                writer.writerow({
                    "mobile": "Other Bus",
                    "route": "Route B",
                    "origin_stop": "Unknown",
                    "origin_stop_latitude": "56.00000",
                    "origin_stop_longitude": "-2.00000",
                    "destination_stop": "Known",
                    "destination_stop_latitude": "56.00000",
                    "destination_stop_longitude": "-2.00000",
                })

            issues = validate.validate_route_trip_files(data_dir)

            self.assertEqual(2, len(issues))
            self.assertTrue(any("route (sample, Other Bus, Route B)" in issue for issue in issues))
            self.assertTrue(any("origin stop (Unknown" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()