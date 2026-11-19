# Geocoding & Spatial Standards

This document outlines the geocoding rules, coordinate precision standards, and spatial boundary gating enforced across all mobile library datasets in this repository.

---

## 1. Coordinate Precision Standard

All coordinates (`GeoX` longitude and `GeoY` latitude) are normalized to **5 decimal places** (e.g. `53.02340`, `-3.56120`).

### Why 5 Decimal Places?
- **Ground Resolution:** At UK latitudes (50°–58° N), 5 decimal places represents roughly **1.1 metres** north-south and **0.6–0.7 metres** east-west.
- **Physical Fit:** Mobile library vehicles are heavy commercial vehicles (typically 8 to 12 metres long and 2.5 metres wide). 5 decimal places lands accurately within the physical parking bay, layby, or school turnaround area without introducing false millimetre-level precision.
- **Data Footprint:** It minimizes file size across the nationwide CSV and GeoJSON datasets and prevents diff churn.

---

## 2. Spatial Bounding Box Gating

To prevent automated geocoding hallucinations (e.g. homonym villages resolving to another county, country, or overseas continent):

1. **Bounding Box Registry (`geocache/authority_bboxes.json`):**
   - Every library authority has an authoritative spatial bounding box envelope (`min_lat`, `max_lat`, `min_lon`, `max_lon`) derived from ONS / OS OpenData boundaries.
2. **Automated Gating:**
   - Both `scripts/_common.py` (`is_in_bbox()`) and `scripts/geocoder.py` enforce these bounds on all candidate locations returned by external APIs (Postcodes.io, Nominatim, OS Open Names).
   - Any candidate coordinates falling outside the authority's spatial envelope are automatically rejected.
3. **Fail-Safe Blanking:**
   - When an address cannot be accurately placed within the verified bounds, coordinates remain blank (`""`) rather than placing a point in an incorrect location.

---

## 3. Persistent Geocache (`geocache/stops_reference.json`)

To ensure reproducibility, minimize external network requests, and preserve manually verified curb pin drops:

- **Structure:** Keyed by normalized `f"{authority}::{community}::{stop}"` and `f"{authority}::{stop}"`.
- **Precedence:** Geocoders check `stops_reference.json` before making external HTTP queries.
- **Curated Pin Drops:** Complex roadside halts, crofting townships, and rural halts without distinct postcodes (e.g., Highland crofts, remote farm cottages, urban road junctions) are permanently recorded in this reference file with their verified coordinates.
