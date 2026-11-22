# Location and map coordinates

This guide explains how mobile library stop locations are found, how accurate the coordinates are, and how we check that stops are in the right place.

## Levels of coordinate accuracy

Not all coordinates have the same level of precision. Depending on the information published by the council, stops fall into one of four accuracy levels:

1. **Exact stop or parking space (within 1 to 10 metres):**
   * The pin is placed directly on the parking bay, village hall car park, school gate, or road layby where the van actually stops.
   * Sourced directly from council map layers (such as ArcGIS or web maps), what3words locations, or manual aerial checks.
2. **Named building or landmark (within 10 to 30 metres):**
   * The pin is placed on the building or facility named in the timetable (such as "Stanton Drew Village Hall" or "Ubley Primary School") using OpenStreetMap or Ordnance Survey data.
3. **Postcode area centre (within 50 to 200 metres):**
   * The pin is placed at the centre of the stop's postcode using Postcodes.io or Code-Point Open. In towns, this is usually very close to the stop. In large rural postcodes, it can be a short walk away.
4. **Village or community centre (within 500 metres to 2 kilometres):**
   * Used as a temporary fallback when a council lists only a village name without a street, building, or postcode.

Currently, across the 8,195 stops in the UK dataset:
* Around 35% are at exact stop or building level.
* Around 33% are at postcode centre level.
* Around 32% are at village or community centre level (mostly in rural areas where councils do not publish postcodes).

## How the script finds coordinates

When an authority script runs, it looks for coordinates in this order of priority:

1. **Saved list of verified stops:**
   * It checks `geocache/stops_reference.json` first. If someone has already researched and verified the exact parking spot for that stop, those coordinates are used.
2. **Council map layers:**
   * If the council publishes an interactive map or GIS feed (such as an ArcGIS FeatureServer), the script extracts the exact coordinates directly from the council's data.
3. **Named building search:**
   * If the stop names a specific building (like a village hall, community centre, or school), the script looks for that building in OpenStreetMap within the council's area.
4. **Postcode lookup:**
   * If a valid UK postcode is available, the script looks up the postcode on Postcodes.io to get its geographic centre.
5. **Village or community lookup:**
   * If no postcode or building is available, the script looks up the community or village name to find its central coordinates.

## Why coordinates use 5 decimal places

All coordinates (`GeoX` longitude and `GeoY` latitude) are stored to **5 decimal places** (for example, `53.02340` and `-3.56120`).

Here is why:
* **The right size:** In the UK, 5 decimal places is accurate to about 1 metre. A mobile library is a large vehicle (usually 8 to 11 metres long), so 1 metre is accurate enough to pinpoint the exact parking bay, village hall layby, or school gates.
* **Avoiding false precision:** Using 7 or 8 decimal places would suggest we know where the van parks down to the nearest millimetre, which is unrealistic.
* **Smaller file sizes:** Keeping coordinates to 5 decimal places keeps the files compact and easy to download.

## Keeping stops within council boundaries

Sometimes different places across the country share the same name (for example, there is a Newport in Wales, Shropshire, and the Isle of Wight).

To stop computer tools from placing a stop in the wrong county:
1. **Boundary boxes:** Every council has an official boundary area stored in `geocache/authority_bboxes.json`.
2. **Automatic checking:** When an address is converted into map coordinates, the script checks whether the coordinates fall inside that council's area. If they fall outside, they are rejected.
3. **Leaving unknown spots blank:** If a location cannot be verified with confidence, we leave the coordinates blank rather than guessing or putting a pin in the wrong place.

## How we can improve accuracy

We are actively working to upgrade stops from postcode or village level to exact building and parking space coordinates:

1. **Scraping council interactive maps:**
   * Many councils publish PDF brochures for the public, but also have public GIS maps or web map finders where exact coordinates are stored. We can connect our scrapers directly to these map layers.
2. **Matching community buildings in OpenStreetMap:**
   * Over 2,300 stops (28%) explicitly name a building like a village hall, church, school, or pub. We can search OpenStreetMap for the named building within that community to find its exact building outline and car park.
3. **What3words in council leaflets:**
   * Some councils (such as Highland and Cornwall) print what3words addresses in their timetables. Converting these gives an exact 3-metre square location.
4. **Local knowledge and manual checks:**
   * Contributors can check stops using satellite imagery or street-level photos to find the actual layby or parking bay, and save the coordinates to `geocache/stops_reference.json`.
