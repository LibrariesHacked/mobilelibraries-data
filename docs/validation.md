# Data Validation & Quality Assurance

This repository enforces Frictionless Data standards, Table Schema constraints, and spatial boundary checks across all datasets.

---

## 1. Automated Validation (`scripts/validate.py`)

Run the project test suite from the repository root:

```bash
python scripts/validate.py
```

This verifies:
1. **Frictionless Data Package Integrity:** Validates [`datapackage.json`](../datapackage.json) and all 50 declared resources against Frictionless specs.
2. **Coordinate Precision:** Ensures all stop coordinates are formatted to exactly 5 decimal places (~1.1 m resolution) and fall within valid UK/ROI bounds.
3. **Recurrence Rules (RFC 5545):** Validates all `Frequency` strings against the official RRULE regex pattern.
4. **Exception Dates:** Confirms that `Exceptions` is either empty or contains a comma-separated list of ISO-8601 dates (`YYYY-MM-DD`). Plain text descriptions (e.g. "Public holidays") are rejected.
5. **Chronological Times:** Checks that `Arrival <= Departure` across all stops.

---

## 2. Frictionless CLI Validation

You can also validate directly with the Frictionless framework CLI:

### Validate the Entire Data Package
```bash
python -m frictionless validate datapackage.json
```

### Validate a Single Authority Dataset
```bash
python -m frictionless validate data/conwy.csv --schema schemas/mobile-library-stops.json
```

---

## 3. Continuous Integration (CI)

Automated validation runs via GitHub Actions ([`.github/workflows/monitor.yml`](../.github/workflows/monitor.yml)) on:
* Pushes to any branch.
* Pull requests against `main`.
* Biannual schedule (1 January and 1 July) to detect upstream timetable changes.
* Manual invocation via `workflow_dispatch`.
