# Location and map coordinates

This guide explains how mobile library stop locations are found, how accurate the coordinates need to be, and how we check that stops are in the right council area.

---

## Why coordinates use 5 decimal places

All coordinates (`GeoX` longitude and `GeoY` latitude) are stored to **5 decimal places** (for example, `53.02340` and `-3.56120`).

Here is why:
* **The right size:** In the UK, 5 decimal places is accurate to about 1 metre. A mobile library is a large vehicle (usually 8 to 11 metres long), so 1 metre is accurate enough to pinpoint the exact parking bay, village hall layby, or school gates.
* **Avoiding false precision:** Using 7 or 8 decimal places would suggest we know where the van parks down to the nearest millimetre, which is unrealistic.
* **Smaller file sizes:** Keeping coordinates to 5 decimal places keeps the files compact and easy to download.

---

## Keeping stops within council boundaries

Sometimes different places across the country share the same name (for example, there is a Newport in Wales, Shropshire, and the Isle of Wight).

To stop computer tools from placing a stop in the wrong county:
1. **Boundary boxes:** Every council has an official boundary area stored in `geocache/authority_bboxes.json`.
2. **Automatic checking:** When an address is converted into map coordinates, the script checks whether the coordinates fall inside that council's area. If they fall outside, they are rejected.
3. **Leaving unknown spots blank:** If a location cannot be verified with confidence, we leave the coordinates blank rather than guessing or putting a pin in the wrong place.

---

## Saved verified locations

Many mobile library stops are in rural spots that do not have their own building or unique postcode (such as farm road ends, laybys, or village greens).

We save coordinates that have been verified by hand in `geocache/stops_reference.json`. When a scraper runs:
* It looks up the stop in the saved list first.
* This ensures that manually checked positions are kept safe and stops are consistently plotted in the right place every time the data updates.
