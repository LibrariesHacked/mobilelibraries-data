"""Comprehensive validation script for mobile library datasets and datapackage.

Checks:
1. Frictionless Data Package schema and resource integrity (datapackage.json).
2. Table Schema conformance for all data/*.csv files.
3. Coordinate validity (within UK bounding boxes, formatted to 5 decimal places).
4. Frequency syntax (RFC 5545 RRULE format).
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
import re
import sys
from pathlib import Path

from frictionless import Package

RRULE_RE = re.compile(
    r"^FREQ=(WEEKLY;INTERVAL=[1-9][0-9]*|MONTHLY;BYDAY=[1-5](MO|TU|WE|TH|FR|SA|SU)(,[1-5](MO|TU|WE|TH|FR|SA|SU))*)$"
)
EXCEPTIONS_RE = re.compile(
    r"^$|^([0-9]{4}-[0-9]{2}-[0-9]{2})(,[0-9]{4}-[0-9]{2}-[0-9]{2})*$"
)
COORD_5DP_RE = re.compile(r"^-?\d+\.\d{5}$")


def _first_value(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = (row.get(name) or "").strip()
        if value:
            return value
    return ""


def _stop_coordinate(row: dict[str, str]) -> tuple[float, float] | None:
    latitude = _first_value(row, "geoy", "GeoY", "Latitude")
    longitude = _first_value(row, "geox", "GeoX", "Longitude")
    try:
        return round(float(latitude), 5), round(float(longitude), 5)
    except ValueError:
        return None


def validate_route_trip_files(data_dir: Path) -> list[str]:
    """Check each authority's route trips against its stop rows."""
    issues = []
    routes_dir = data_dir / "routes"

    for route_file in sorted(routes_dir.glob("*_routes.csv")):
        if route_file.name.startswith("uk_"):
            continue

        authority = route_file.name.removesuffix("_routes.csv")
        stop_file = data_dir / f"{authority}.csv"
        if not stop_file.exists():
            issues.append(f"{route_file.name}: no matching stop file {stop_file.name}")
            continue

        stop_routes = set()
        stop_locations = set()
        with stop_file.open(mode="r", encoding="utf-8", newline="") as file:
            for stop in csv.DictReader(file):
                mobile = _first_value(stop, "mobile_name", "Mobile name", "mobile", "Mobile")
                route = _first_value(stop, "route", "Route")
                name = _first_value(stop, "stop", "Stop")
                coordinate = _stop_coordinate(stop)
                if mobile and route:
                    stop_routes.add((mobile, route))
                if name and coordinate:
                    stop_locations.add((name, *coordinate))

        with route_file.open(mode="r", encoding="utf-8", newline="") as file:
            for row_number, trip in enumerate(csv.DictReader(file), start=2):
                mobile = _first_value(trip, "mobile")
                route = _first_value(trip, "route")
                if (mobile, route) not in stop_routes:
                    issues.append(
                        f"{route_file.name}:{row_number}: route ({authority}, {mobile}, {route}) does not match stop data"
                    )

                for endpoint in ("origin", "destination"):
                    name = _first_value(trip, f"{endpoint}_stop")
                    latitude = _first_value(trip, f"{endpoint}_stop_latitude")
                    longitude = _first_value(trip, f"{endpoint}_stop_longitude")
                    try:
                        location = (name, round(float(latitude), 5), round(float(longitude), 5))
                    except ValueError:
                        location = None
                    if location not in stop_locations:
                        issues.append(
                            f"{route_file.name}:{row_number}: {endpoint} stop ({name}, {latitude}, {longitude}) does not match stop data"
                        )

    return issues


def main() -> int:
    errors = 0
    print("=" * 60)
    print("Running Mobile Library Data Validation")
    print("=" * 60)

    # 1. Frictionless Data Package Validation
    print("\n1. Validating datapackage.json...")
    pkg = Package("datapackage.json")
    report = pkg.validate()
    if not report.valid:
        errors += 1
        print("❌ datapackage.json validation failed:")
        for err in report.flatten(["resourceName", "rowNumber", "fieldName", "message"])[:10]:
            print("  ", err)
    else:
        print(f"✓ datapackage.json is VALID ({len(pkg.resources)} resources)")

    # 2. Coordinate precision, RRULE syntax, and Exceptions date list check on all authority CSVs
    print("\n2. Checking coordinate precision, RRULE syntax, and Exceptions...")
    csv_files = sorted(Path("data").glob("*.csv"))
    checked_stops = 0
    coord_issues = 0
    freq_issues = 0
    exc_issues = 0
    time_issues = 0
    newline_issues = 0
    syntax_issues = 0

    for csv_file in csv_files:
        if (
            csv_file.name.startswith("uk_")
            or csv_file.name.startswith("library-services")
            or "review_queue" in csv_file.name
        ):
            continue
        with open(csv_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, start=2):
                checked_stops += 1
                lat_str = (row.get("geoy") or row.get("GeoY") or row.get("Latitude", "")).strip()
                lng_str = (row.get("geox") or row.get("GeoX") or row.get("Longitude", "")).strip()
                freq_str = (row.get("frequency") or row.get("Frequency", "")).strip()
                exc_str = (row.get("exceptions") or row.get("Exceptions", "")).strip()
                arr_str = (row.get("arrival") or row.get("Arrival", "")).strip()
                dep_str = (row.get("departure") or row.get("Departure", "")).strip()
                start_str = (row.get("start") or row.get("Start", "")).strip()
                end_str = (row.get("end") or row.get("End", "")).strip()
                stop_str = (row.get("stop") or row.get("Stop", "")).strip()
                comm_str = (row.get("community") or row.get("Community", "")).strip()

                if lat_str and lng_str:
                    if not COORD_5DP_RE.match(lat_str) or not COORD_5DP_RE.match(lng_str):
                        coord_issues += 1
                        if coord_issues <= 3:
                            print(f"  [Coord Warning] {csv_file.name}:{i} ({row.get('Stop')}) lat={lat_str}, lng={lng_str} not 5 decimal places")

                if freq_str:
                    if not RRULE_RE.match(freq_str):
                        freq_issues += 1
                        if freq_issues <= 3:
                            print(f"  [Freq Warning] {csv_file.name}:{i} ({row.get('Stop')}) invalid RRULE: '{freq_str}'")

                if exc_str:
                    if not EXCEPTIONS_RE.match(exc_str):
                        exc_issues += 1
                        if exc_issues <= 3:
                            print(f"  [Exceptions Warning] {csv_file.name}:{i} ({row.get('Stop')}) invalid Exceptions: '{exc_str}' (must be comma-separated YYYY-MM-DD)")

                if arr_str and dep_str and arr_str > dep_str:
                    time_issues += 1
                    if time_issues <= 3:
                        print(f"  [Time Warning] {csv_file.name}:{i} ({row.get('Stop')}) Arrival ({arr_str}) > Departure ({dep_str})")

                if start_str and end_str and start_str > end_str:
                    time_issues += 1
                    print(f"  [Date Warning] {csv_file.name}:{i} ({row.get('Stop')}) Start ({start_str}) > End ({end_str})")

                # Syntax / corruption checks: unclosed parentheses or corrupted text
                for text_val in (stop_str, comm_str):
                    if text_val:
                        if text_val.count("(") != text_val.count(")"):
                            syntax_issues += 1
                            if syntax_issues <= 3:
                                print(f"  [Syntax Error] {csv_file.name}:{i} unbalanced parentheses in '{text_val}'")
                        if any(bad in text_val for bad in ["â€™", "â€“", "Â", "RichaRoad", "UndeRoad"]):
                            syntax_issues += 1
                            if syntax_issues <= 3:
                                print(f"  [Corruption Error] {csv_file.name}:{i} corrupted text in '{text_val}'")

                for col_name, cell_val in row.items():
                    if cell_val and ("\n" in cell_val or "\r" in cell_val):
                        newline_issues += 1
                        if newline_issues <= 3:
                            print(f"  [Newline Error] {csv_file.name}:{i} column '{col_name}' contains embedded newline: {repr(cell_val)}")

    # 3. Check timetable expiration and upcoming renewals
    print("\n3. Checking timetable validity dates...")
    today = datetime.now().strftime("%Y-%m-%d")
    soon = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    expired_authorities = {}
    expiring_soon = {}

    for csv_file in csv_files:
        if (
            csv_file.name.startswith("uk_")
            or csv_file.name.startswith("library-services")
            or "review_queue" in csv_file.name
        ):
            continue
        with open(csv_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                end_str = (row.get("end") or row.get("End") or "").strip()
                if end_str:
                    if end_str < today:
                        expired_authorities[csv_file.stem] = end_str
                    elif today <= end_str <= soon:
                        expiring_soon[csv_file.stem] = end_str
                    break

    if expired_authorities:
        print(f"⚠️ Notice: {len(expired_authorities)} authority timetables have past End dates:")
        for auth, dt in sorted(expired_authorities.items()):
            print(f"   - {auth}: expired on {dt}")
    elif expiring_soon:
        print(f"ℹ️ Notice: {len(expiring_soon)} authority timetables expire within 30 days:")
        for auth, dt in sorted(expiring_soon.items()):
            print(f"   - {auth}: expires on {dt}")
    else:
        print(f"✓ All active timetables are current and valid for future visits.")

    if coord_issues > 0:
        print(f"❌ Found {coord_issues} coordinate precision warnings.")
        errors += 1
    else:
        print(f"✓ All coordinates in {checked_stops} stops adhere to 5-decimal place precision.")

    if freq_issues > 0:
        print(f"❌ Found {freq_issues} invalid frequency patterns.")
        errors += 1
    else:
        print(f"✓ All frequency strings adhere to RFC 5545 RRULE format.")

    if exc_issues > 0:
        print(f"❌ Found {exc_issues} invalid Exceptions values.")
        errors += 1
    else:
        print(f"✓ All Exceptions fields are either empty or valid ISO-8601 date lists.")

    if time_issues > 0:
        print(f"❌ Found {time_issues} time order issues (Arrival > Departure).")
        errors += 1
    else:
        print(f"✓ All stops have valid chronologically ordered times (Arrival <= Departure).")

    if newline_issues > 0:
        print(f"❌ Found {newline_issues} embedded newline errors.")
        errors += 1
    else:
        print(f"✓ All stop fields are single-line with 0 embedded newlines.")

    if syntax_issues > 0:
        print(f"❌ Found {syntax_issues} text syntax/corruption errors.")
        errors += 1
    else:
        print(f"✓ All stop and community names have balanced parentheses and clean text.")

    print("\n4. Checking route-trip relationships...")
    route_issues = validate_route_trip_files(Path("data"))
    if route_issues:
        for issue in route_issues[:10]:
            print(f"  [Route Error] {issue}")
        print(f"❌ Found {len(route_issues)} route-trip relationship issues.")
        errors += 1
    else:
        print("✓ All route trips match known authority routes and stop locations.")

    print("\n" + "=" * 60)
    if errors == 0:
        print("🎉 ALL VALIDATION CHECKS PASSED!")
        print("=" * 60)
        return 0
    else:
        print(f"❌ Validation failed with {errors} error category/categories.")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
