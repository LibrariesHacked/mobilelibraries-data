# Authority Services Registry (`services.csv`)

[`services.csv`](../services.csv) is the master administrative register tracking mobile library provision across all **216 UK library authorities**.

---

## Schema & Core Fields

The file adheres to the Frictionless schema defined in [`datapackage.json`](../datapackage.json):

| Field | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `local_authority` | string | Common name of the local authority | `Conwy` |
| `official_name` | string | Full legal administrative name | `Conwy County Borough Council` |
| `local_authority_code` | string | Official ONS/GSS administrative identifier | `W06000003` |
| `nation` | string | UK nation (`England`, `Scotland`, `Wales`, `Northern Ireland`) | `Wales` |
| `authority_type` | string | Local government structure (e.g. `Unitary Authority`, `County Council`) | `Unitary Authority` |
| `dataset_slug` | string | Unique filename slug matching `data/<slug>.csv` | `conwy` |
| `has_mobile_service` | string | `Yes` or `No` | `Yes` |
| `status` | string | Provision status category (see below) | `Active Verified` |
| `source_url` | string | Official council timetable or service web page | `https://www.conwy.gov.uk/...` |
| `last_checked` | date | Date the service website was last inspected | `2026-11-19` |
| `last_updated` | date | Date the timetable data was last updated | `2026-11-19` |
| `notes` | string | Operational context, vehicle fleet info, or discontinuation notes | `2-vehicle fleet; 3-weekly rota` |

---

## Provision Status Categories

Every authority is classified into one of the following verified statuses:

1. **`Active Verified` (50 authorities):**
   - Service is actively operating with public scheduled timetables harvested and maintained in `data/<slug>.csv`.
2. **`No Mobile (Urban/Home Delivery)` (123 authorities):**
   - The authority operates static branches and/or Home Library Delivery services for vulnerable residents, but no mobile library vehicle.
3. **`Discontinued` (34 authorities):**
   - The authority previously operated mobile library routes, but the service was decommissioned or replaced with community hubs/postal delivery.
4. **`Active (No Public Timetable)` (2 authorities):**
   - Active mobile vehicles exist, but service visits are arranged privately, on-demand, or restricted to schools/nursing homes without fixed public timetables (e.g. Isle of Anglesey, Ceredigion).
5. **`Active - On Demand` (1 authority):**
   - On-demand mobile service (Comhairle nan Eilean Siar / Western Isles).
6. **`Dissolved Historic Council` (4 authorities):**
   - Historic administrative entities abolished during local government reorganisation.
