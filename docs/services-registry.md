# List of all UK library services

The [`services.csv`](../services.csv) file is a master list tracking mobile library provision across all **216 library authorities** in the UK.

It records whether each council operates a mobile library van, links to their timetable pages, and notes services that have closed or changed over time.

---

## Columns in services.csv

| Column | What it means | Example |
| :--- | :--- | :--- |
| `local_authority` | Common name of the council | `Conwy` |
| `official_name` | Full legal name of the council | `Conwy County Borough Council` |
| `local_authority_code` | Official 9-character code from the Office for National Statistics | `W06000003` |
| `nation` | UK nation (`England`, `Scotland`, `Wales`, or `Northern Ireland`) | `Wales` |
| `authority_type` | Council type (such as `County Council` or `Unitary Authority`) | `Unitary Authority` |
| `dataset_slug` | Short name matching the filename in `data/` and `scripts/` | `conwy` |
| `has_mobile_service` | Whether the council currently runs a mobile library (`Yes` or `No`) | `Yes` |
| `status` | Category explaining service status (see below) | `Active Verified` |
| `source_url` | Web link to the council's timetable or consultation page | `https://www.conwy.gov.uk/...` |
| `last_checked` | Date the website was last checked by us | `2026-11-19` |
| `last_updated` | Date the timetable data was last updated | `2026-11-19` |
| `notes` | Extra context, such as vehicle numbers or reasons for closure | `2 vehicles; 3-weekly cycle` |

---

## Mobile service status types

Every council is given one of these verified statuses:

1. **`Active Verified` (50 councils):**
   * The council currently runs a mobile library and publishes a timetable of public stops. Data is collected and kept up to date in `data/<council>.csv`.
2. **`No Mobile (Urban/Home Delivery)` (123 councils):**
   * The council does not operate a mobile library vehicle. Most of these are city and town councils where residents live close to a physical library building, or councils that deliver books directly to people's homes.
3. **`Discontinued` (34 councils):**
   * The council used to run a mobile library, but the service has closed down.
4. **`Active (No Public Timetable)` (2 councils):**
   * A mobile van exists, but stops are not published as a fixed public timetable (for example, stops visit schools, care homes, or are booked privately).
5. **`Active - On Demand` (1 council):**
   * Mobile services that visit communities when residents request them (such as in the Western Isles).
6. **`Dissolved Historic Council` (4 councils):**
   * Older councils that no longer exist due to local government mergers.
