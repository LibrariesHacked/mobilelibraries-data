# Contributing Guide

Contributions to improve data accuracy, add new authorities, or fix timetable changes are very welcome.

---

## Adding or Updating an Authority

### 1. Creating a Harvester Script
Each authority has a dedicated script in `scripts/<slug>.py` (matching the `dataset_slug` in `services.csv`).

Always import shared helper utilities from [`scripts/_common.py`](../scripts/_common.py) rather than reimplementing them:

```python
from pathlib import Path
from _common import (
    create_mobile_library_file,
    save_raw,
    get_html,
    clean_time_24h,
    parse_time_range,
    normalise_postcode,
    batch_lookup_postcodes,
    validate_dataset
)
from geocoder import Geocoder
```

### 2. Follow Schema Guidelines
- **All 19 Schema Columns:** Ensure every required column in [`docs/schema.md`](schema.md) is populated.
- **24-Hour Times:** All times must be zero-padded `HH:MM` in 24-hour clock (use `clean_time_24h`).
- **Postcodes:** Validated UK format with single space (use `normalise_postcode`).
- **Coordinates:** Standardized to **5 decimal places** (use `round(float(val), 5)`).
- **Recurrence Rules:** The `Frequency` column must strictly use RFC 5545 RRULE format (e.g. `FREQ=WEEKLY;INTERVAL=2`).

### 3. Preserving Raw Timetable Snapshots
Save downloaded PDF or HTML source documents to `raw/<slug>/<YYYY-MM-DD>/` using `save_raw()`. This ensures all transformations can be inspected and run offline for verification.

### 4. Rebuilding Aggregations
After creating or updating an authority CSV:
1. Run `python scripts/<slug>.py` to generate `data/<slug>.csv`.
2. Run `python scripts/combine.py` to regenerate the nationwide `uk_mobile_library_stops.csv` and GeoJSON.
3. Validate the Data Package:
   ```bash
   frictionless validate datapackage.json
   ```

---

## Submitting Pull Requests

1. Fork the repo and create your branch from `main`:
   ```bash
   git checkout -b feature/update-<slug>
   ```
2. Verify all tests pass:
   ```bash
   python -m pytest tests/  # or run Frictionless validation
   frictionless validate datapackage.json
   ```
3. Commit your changes with a clear commit message.
4. Open a Pull Request referencing the authority updated.
