# How to contribute

We welcome contributions to help keep mobile library data accurate, add new councils, or fix timetable changes.

---

## Adding or updating a council

### 1. Creating a council script

Each council has its own script in `scripts/<council_name>.py`.

When writing or updating a script, use the shared helper functions in [`scripts/_common.py`](../scripts/_common.py) to save time:

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

### 2. Following the data format

* **All 19 columns:** Make sure your output matches the columns in [data schema and visit frequency](schema.md).
* **Times:** Use the 24-hour clock (such as `10:15` or `14:30`).
* **Postcodes:** Use standard UK postcode formatting with a single space (such as `LL21 4ST`).
* **Coordinates:** Format latitude and longitude to 5 decimal places (like `53.02340`).
* **Visit frequency:** Record cycles using standard calendar rules (such as `FREQ=WEEKLY;INTERVAL=2` for visits every two weeks).

### 3. Saving raw timetable files

Always save a copy of the original timetable document (HTML, PDF, or data file) into `raw/<council>/<YYYY-MM-DD>/` using `save_raw()`. This provides a permanent record and allows anyone to verify the data offline.

### 4. Updating the combined files

After generating or updating a council file:
1. Run `python scripts/<council_name>.py` to create or update `data/<council_name>.csv`.
2. Run `python scripts/combine.py` to update the UK-wide files.
3. Check the data:
   ```bash
   python scripts/validate.py
   ```

---

## Submitting your changes

1. Fork the repository and create your branch from `main`:
   ```bash
   git checkout -b feature/update-<council_name>
   ```
2. Make your changes and run `python scripts/validate.py` to ensure all checks pass.
3. Commit your changes with a clear commit message.
4. Open a pull request describing the changes you made.
