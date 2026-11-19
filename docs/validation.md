# Data checking and quality

This guide explains how we check that the data is accurate, complete, and properly formatted before it is published.

---

## 1. Running the automated test script

You can test all datasets by running a single command from your terminal:

```bash
python scripts/validate.py
```

This checks the following:
* **File structure:** Verifies that every file has the expected 19 columns and passes the rules set in [`datapackage.json`](../datapackage.json).
* **Map coordinates:** Confirms that all coordinates are formatted to 5 decimal places and fall inside the UK or Ireland.
* **Visit schedules:** Checks that recurrence rules (like weekly or monthly visits) follow standard calendar rules.
* **Holiday closures:** Ensures that any exception dates are written as clean dates (`YYYY-MM-DD`) rather than plain text words like "Bank holidays".
* **Chronological times:** Verifies that arrival times always come before departure times for every stop.

---

## 2. Checking with the Frictionless tool

You can also use the Frictionless Data tool directly:

### Check the entire data package
```bash
python -m frictionless validate datapackage.json
```

### Check a single council file
```bash
python -m frictionless validate data/conwy.csv --schema schemas/mobile-library-stops.json
```

---

## 3. Automated checks on GitHub

Every time changes are pushed or a pull request is submitted, an automated workflow ([`.github/workflows/monitor.yml`](../.github/workflows/monitor.yml)) runs these checks automatically. This ensures no errors or broken files make it into the repository.
