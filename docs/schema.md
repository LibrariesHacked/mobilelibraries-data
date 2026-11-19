# Data schema and visit frequency

This guide explains how mobile library stops are stored in the data files, what each column means, and how repeating timetables are written.

The formal specification is stored in [`schemas/mobile-library-stops.json`](../schemas/mobile-library-stops.json).

## Stop columns and descriptions

Every council file in `data/<council>.csv` and the combined nationwide file `data/uk_mobile_library_stops.csv` uses the same 19 columns:

| Column | Type | Is it required? | What it means | Example |
| :--- | :--- | :--- | :--- | :--- |
| `Local authority` | text | Yes | The council responsible for the service | `Conwy County Borough Council` |
| `Local authority code` | text | Yes | Official 9-character council code (from the ONS) | `W06000003` |
| `Mobile name` | text | Yes | Name of the van or mobile vehicle | `Mobile Library 1` |
| `Route` | text | Yes | Name or identifier for the route schedule | `Week 1 Tuesday` |
| `Community` | text | Optional | Village, town, parish, or neighbourhood | `Cerrigydrudion` |
| `Stop` | text | Yes | Exact place where the van parks | `Parish Hall Car Park` |
| `Address` | text | Optional | Street address or helpful directions | `High Street, Cerrigydrudion` |
| `Postcode` | text | Optional | Nearest UK postcode | `LL21 4ST` |
| `GeoX` | number | Optional | Longitude coordinate (how far east or west) | `-3.56120` |
| `GeoY` | number | Optional | Latitude coordinate (how far north or south) | `53.02340` |
| `Day` | text | Yes | Day of the week the van visits | `Tuesday` |
| `Type` | text | Yes | Usually `Public` (available to everyone) | `Public` |
| `Arrival` | time | Yes | When the van arrives (24-hour clock, HH:MM) | `10:15` |
| `Departure` | time | Yes | When the van leaves (24-hour clock, HH:MM) | `11:00` |
| `Frequency` | text | Yes | How often the visit repeats (see below) | `FREQ=WEEKLY;INTERVAL=3` |
| `Start` | date | Yes | First date this timetable applies from | `2026-01-05` |
| `End` | date | Optional | Last date this timetable applies to (if known) | `2026-12-23` |
| `Exceptions` | text | Optional | Specific dates when the van will not visit | `2026-05-04,2026-05-25` |
| `Timetable` | link | Optional | Web address for the council's timetable page | `https://www.conwy.gov.uk/...` |

## How exceptions and closures are written

The `Exceptions` column lists specific dates when a scheduled stop will not happen (for example, on a bank holiday or when a van is in for servicing).

* **Format:** Dates must be written as a comma-separated list in year-month-day order (`YYYY-MM-DD`). For example: `2026-05-04,2026-05-25`.
* **No plain text words:** General phrases like `"Public holidays"`, `"Bank holidays"`, or `"Closed over Christmas"` cannot be used here.
* **If dates are not published:** If the council only says "does not run on public holidays" without listing specific dates, leave this column blank.

## How visit frequency is recorded

Mobile libraries visit stops on a repeating cycle (such as every week, every two weeks, or on the first Monday of each month). We record this using the standard calendar format (iCalendar RFC 5545).

### Weekly and multi-weekly cycles

Most mobile library stops happen at a regular number of weeks on the named `Day`:

| Cycle | How it is written | What it means |
| :--- | :--- | :--- |
| **Every week** | `FREQ=WEEKLY;INTERVAL=1` | The van visits every single week |
| **Every two weeks** | `FREQ=WEEKLY;INTERVAL=2` | The van visits fortnightly |
| **Every three weeks** | `FREQ=WEEKLY;INTERVAL=3` | The van visits every 3 weeks |
| **Every four weeks** | `FREQ=WEEKLY;INTERVAL=4` | The van visits every 4 weeks |

### Monthly patterns by day of the week

Some services visit on a specific week of each month:

| Pattern | How it is written | What it means |
| :--- | :--- | :--- |
| **First Monday** | `FREQ=MONTHLY;BYDAY=1MO` | Visits on the first Monday of each month |
| **Third Thursday** | `FREQ=MONTHLY;BYDAY=3TH` | Visits on the third Thursday of each month |
| **Second and fourth Wednesday** | `FREQ=MONTHLY;BYDAY=2WE,4WE` | Visits on both the 2nd and 4th Wednesdays |
