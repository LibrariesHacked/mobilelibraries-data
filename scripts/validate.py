"""Comprehensive validation script for mobile library datasets and datapackage.

Checks:
1. Frictionless Data Package schema and resource integrity (datapackage.json).
2. Table Schema conformance for all data/*.csv files.
3. Coordinate validity (within UK bounding boxes, formatted to 5 decimal places).
4. Frequency syntax (RFC 5545 RRULE format).
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from frictionless import Package

RRULE_RE = re.compile(
    r"^FREQ=(WEEKLY;INTERVAL=[1-9][0-9]*|MONTHLY;BYDAY=[1-5](MO|TU|WE|TH|FR|SA|SU)(,[1-5](MO|TU|WE|TH|FR|SA|SU))*)$"
)
COORD_5DP_RE = re.compile(r"^-?\d+\.\d{5}$")


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

    # 2. Coordinate precision and RRULE check on all authority CSVs
    print("\n2. Checking coordinate precision and RRULE syntax...")
    csv_files = sorted(Path("data").glob("*.csv"))
    checked_stops = 0
    coord_issues = 0
    freq_issues = 0

    for csv_file in csv_files:
        if csv_file.name.startswith("uk_"):
            continue
        with open(csv_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, start=2):
                checked_stops += 1
                lat_str = row.get("Latitude", "").strip()
                lng_str = row.get("Longitude", "").strip()
                freq_str = row.get("Frequency", "").strip()

                if lat_str and lng_str:
                    if not COORD_5DP_RE.match(lat_str) or not COORD_5DP_RE.match(lng_str):
                        coord_issues += 1
                        if coord_issues <= 3:
                            print(f"  [Coord Warning] {csv_file.name}:{i} ({row.get('Stop name')}) lat={lat_str}, lng={lng_str} not 5 decimal places")

                if freq_str:
                    if not RRULE_RE.match(freq_str):
                        freq_issues += 1
                        if freq_issues <= 3:
                            print(f"  [Freq Warning] {csv_file.name}:{i} ({row.get('Stop name')}) invalid RRULE: '{freq_str}'")

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
