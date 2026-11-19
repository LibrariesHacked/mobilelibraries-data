# Data Schema & Recurrence Rules

This repository publishes mobile library stop and schedule data conforming to the [Frictionless Table Schema](https://specs.frictionlessdata.io/table-schema/) standard.

The primary schema definition is maintained in [`schemas/mobile-library-stops.json`](../schemas/mobile-library-stops.json).

---

## Stops Data Dictionary

Every authority stops dataset in `data/<slug>.csv` and the combined dataset `data/uk_mobile_library_stops.csv` contains the following 19 columns:

| Field | Type | Format | Constraints | Description | Example |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `Local authority` | string | default | required | Official administrative name of the library authority | `Conwy County Borough Council` |
| `Local authority code`| string | default | regex: `^[ENSW][0-9]{8}$` | Official ONS/GSS administrative identifier | `W06000003` |
| `Mobile name` | string | default | required | Vehicle identifier or mobile service name | `Mobile Library 1` |
| `Route` | string | default | required | Route or schedule grouping identifier | `Week 1 Tuesday` |
| `Community` | string | default | optional | Town, village, parish, or district | `Cerrigydrudion` |
| `Stop` | string | default | required | Specific stopping place, facility, or landmark | `Parish Hall Car Park` |
| `Address` | string | default | optional | Full postal address or location description | `High Street, Cerrigydrudion` |
| `Postcode` | string | default | optional (valid UK postcode) | Postcode of stop location | `LL21 4ST` |
| `GeoX` | number | default | optional (-9.0 to 2.5) | Longitude in decimal degrees (WGS84, 5 decimal places) | `-3.56120` |
| `GeoY` | number | default | optional (49.0 to 61.5) | Latitude in decimal degrees (WGS84, 5 decimal places) | `53.02340` |
| `Day` | string | default | enum: `Monday`..`Sunday` | Day of the week for the stop | `Tuesday` |
| `Type` | string | default | enum: `Public`, `Private`, `Dynamic`, `Other` | Access type of the stop | `Public` |
| `Arrival` | time | `%H:%M` | required | Scheduled arrival time in 24-hour clock | `10:15` |
| `Departure` | time | `%H:%M` | required | Scheduled departure time in 24-hour clock | `11:00` |
| `Frequency` | string | default | RFC 5545 RRULE | Frequency format for recurrence | `FREQ=WEEKLY;INTERVAL=3` |
| `Start` | date | `%Y-%m-%d`| required | Start date of current timetable period | `2026-01-05` |
| `End` | date | `%Y-%m-%d`| optional | End date of timetable period (if defined) | `2026-12-23` |
| `Exceptions` | string | default | optional | Comma-separated ISO-8601 dates (`YYYY-MM-DD`) on which this stop is not visited. Plain text like 'Public holidays' is prohibited. | `2026-05-04,2026-05-25` |
| `Timetable` | string | uri | optional | Official source URL where timetable is published | `https://www.conwy.gov.uk/...` |

---

## Exceptions Field Format

Following the official [schema.librarydata.uk mobile library stops specification](https://schema.librarydata.uk/mobile-library-stops):
- **Allowed values:** Either completely empty (`""`) or a comma-separated list of ISO-8601 dates in `YYYY-MM-DD` format (e.g. `2026-05-04,2026-05-25`).
- **Prohibited:** Descriptive text phrases such as `"Public holidays"`, `"Bank holidays"`, `"Christmas period"`, or `"Week 1 Monday (maintenance)"` are strictly prohibited.
- **Rule of thumb:** If the authority provides a general statement (e.g. "mobile libraries do not run on bank holidays") without listing explicit dates, leave the `Exceptions` field empty. If explicit closure dates are scheduled, format each as `YYYY-MM-DD`.

---

## Recurrence Rule Format (RFC 5545)

The `Frequency` field strictly follows the **iCalendar RFC 5545 RRULE** recurrence rule specification:

### 1. Weekly & Multi-Weekly Cycles

Used when stops recur at fixed interval intervals of weeks on the specified `Day`:

| Pattern | RFC 5545 RRULE | Meaning |
| :--- | :--- | :--- |
| **Weekly** | `FREQ=WEEKLY;INTERVAL=1` | Visits occur once every week |
| **Fortnightly** | `FREQ=WEEKLY;INTERVAL=2` | Visits occur every two weeks |
| **3-Weekly** | `FREQ=WEEKLY;INTERVAL=3` | Visits occur every three weeks |
| **4-Weekly** | `FREQ=WEEKLY;INTERVAL=4` | Visits occur every four weeks |

### 2. Monthly Cycles by Weekday Pattern

Used when stops visit on specific nth weekdays of each month:

| Pattern | RFC 5545 RRULE | Meaning |
| :--- | :--- | :--- |
| **1st Monday** | `FREQ=MONTHLY;BYDAY=1MO` | Visits the first Monday of each month |
| **3rd Thursday** | `FREQ=MONTHLY;BYDAY=3TH` | Visits the third Thursday of each month |
| **2nd & 4th Wednesday** | `FREQ=MONTHLY;BYDAY=2WE,4WE` | Visits on both 2nd and 4th Wednesdays |
| **Last Friday** | `FREQ=MONTHLY;BYDAY=-1FR` | Visits the final Friday of each month |

Validation regex used in test suites:
```regex
^FREQ=(WEEKLY;INTERVAL=[1-9][0-9]*|MONTHLY;BYDAY=-?[1-5](MO|TU|WE|TH|FR|SA|SU)(,-?[1-5](MO|TU|WE|TH|FR|SA|SU))*)$
```
