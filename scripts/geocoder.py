"""
Unified Geocoding Engine with Reference Cache and Hierarchy Resolution.

Priority resolution strategy:
1. Exact reference cache lookup (from previously verified stops: auth::comm::stop).
2. Stop name reference lookup within authority (auth::stop).
3. Postcode lookup via Postcodes.io (if full UK postcode provided).
4. Community / place resolution via Postcodes.io places API.
5. Fallback geocoding via OpenStreetMap Nominatim.
6. Local cache preservation in geocache/stops_reference.json.
"""

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / 'geocache'
CACHE_FILE = CACHE_DIR / 'stops_reference.json'
PLACES_CACHE_FILE = CACHE_DIR / 'places_cache.json'
BBOX_FILE = CACHE_DIR / 'authority_bboxes.json'


def normalise_key(text):
    """Lowercase text and strip non-alphanumeric characters for cache key matching."""
    if not text:
        return ''
    return re.sub(r'[^a-z0-9]', '', str(text).lower())


class Geocoder:
    def __init__(self):
        """Initialize stop and place caches and load existing JSON cache files."""
        self.reference_stops = {}
        self.places_cache = {}
        self.bboxes = {}
        self._load_caches()

    def _load_caches(self):
        """Load persisted reference stop and place caches from disk if present."""
        if CACHE_FILE.exists():
            try:
                self.reference_stops = json.loads(CACHE_FILE.read_text(encoding='utf-8'))
            except Exception as e:
                print(f"Warning: could not read {CACHE_FILE}: {e}")

        if PLACES_CACHE_FILE.exists():
            try:
                self.places_cache = json.loads(PLACES_CACHE_FILE.read_text(encoding='utf-8'))
            except Exception as e:
                print(f"Warning: could not read {PLACES_CACHE_FILE}: {e}")

        if BBOX_FILE.exists():
            try:
                self.bboxes = json.loads(BBOX_FILE.read_text(encoding='utf-8'))
            except Exception as e:
                print(f"Warning: could not read {BBOX_FILE}: {e}")

    def get_bbox(self, authority):
        """Lookup bounding box for authority name or slug."""
        if not authority:
            return None
        slug = re.sub(r'[^a-z0-9]+', '_', authority.lower()).strip('_')
        if slug in self.bboxes:
            return self.bboxes[slug]
        norm = normalise_key(authority)
        for k, v in self.bboxes.items():
            if normalise_key(k) == norm or normalise_key(k) in norm or norm in normalise_key(k):
                return v
        return None

    def is_in_bbox(self, lat, lon, bbox):
        """Return True if (lat, lon) is within bbox."""
        if not bbox or lat is None or lon is None:
            return True
        try:
            lat, lon = float(lat), float(lon)
        except (ValueError, TypeError):
            return False
        return (bbox.get('min_lat', -90) <= lat <= bbox.get('max_lat', 90) and
                bbox.get('min_lon', -180) <= lon <= bbox.get('max_lon', 180))

    def save_caches(self):
        """Write reference_stops and places_cache dictionaries to disk as JSON."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(self.reference_stops, indent=2), encoding='utf-8')
        PLACES_CACHE_FILE.write_text(json.dumps(self.places_cache, indent=2), encoding='utf-8')

    def resolve(self, authority, community, stop, postcode='', address=''):
        """
        Attempts to resolve GeoX (longitude), GeoY (latitude), and full Postcode.
        Returns dict: {'geox': float, 'geoy': float, 'postcode': str, 'source': str}
        """
        auth_k = normalise_key(authority)
        comm_k = normalise_key(community)
        stop_k = normalise_key(stop)
        bbox = self.get_bbox(authority)

        # 1. Match full reference key
        full_k = f"{auth_k}::{comm_k}::{stop_k}"
        if full_k in self.reference_stops:
            entry = self.reference_stops[full_k]
            if self.is_in_bbox(entry.get('geoy'), entry.get('geox'), bbox):
                return {
                    'geox': entry['geox'],
                    'geoy': entry['geoy'],
                    'postcode': entry.get('postcode') or postcode,
                    'source': f"ref_cache:{entry.get('source', 'known')}"
                }

        # 2. Match short key (auth + stop)
        short_k = f"{auth_k}::{stop_k}"
        if short_k in self.reference_stops:
            entry = self.reference_stops[short_k]
            if self.is_in_bbox(entry.get('geoy'), entry.get('geox'), bbox):
                return {
                    'geox': entry['geox'],
                    'geoy': entry['geoy'],
                    'postcode': entry.get('postcode') or postcode,
                    'source': f"ref_cache_short:{entry.get('source', 'known')}"
                }

        # 3. Postcode lookup if valid full UK postcode
        clean_pc = postcode.strip().upper()
        # Full UK postcodes consist of outward and inward parts separated by a space
        if clean_pc and len(clean_pc.split()) == 2:
            geo = self._lookup_postcode(clean_pc)
            if geo and self.is_in_bbox(geo.get('geoy'), geo.get('geox'), bbox):
                self.remember_stop(authority, community, stop, geo['geox'], geo['geoy'], clean_pc, 'postcode_api')
                return geo

        # 4. Lookup community/village in places cache or API
        if community:
            place_geo = self._lookup_place(community, authority)
            if place_geo and self.is_in_bbox(place_geo.get('geoy'), place_geo.get('geox'), bbox):
                self.remember_stop(authority, community, stop, place_geo['geox'], place_geo['geoy'], place_geo.get('postcode', ''), 'place_api')
                return place_geo

        # 5. Fallback Nominatim lookup using address + authority
        nom_geo = self._lookup_nominatim(stop, community, authority)
        if nom_geo and self.is_in_bbox(nom_geo.get('geoy'), nom_geo.get('geox'), bbox):
            self.remember_stop(authority, community, stop, nom_geo['geox'], nom_geo['geoy'], nom_geo.get('postcode', ''), 'nominatim')
            return nom_geo

        return {'geox': '', 'geoy': '', 'postcode': clean_pc, 'source': 'none'}

    def remember_stop(self, authority, community, stop, geox, geoy, postcode='', source='runtime'):
        """Save a resolved stop's coordinates in reference_stops under full and short keys."""
        bbox = self.get_bbox(authority)
        if not self.is_in_bbox(geoy, geox, bbox):
            return
        auth_k = normalise_key(authority)
        comm_k = normalise_key(community)
        stop_k = normalise_key(stop)

        entry = {
            'authority': authority,
            'community': community,
            'stop': stop,
            'postcode': postcode,
            'geox': round(float(geox), 5),
            'geoy': round(float(geoy), 5),
            'source': source
        }

        full_k = f"{auth_k}::{comm_k}::{stop_k}"
        short_k = f"{auth_k}::{stop_k}"
        self.reference_stops[full_k] = entry
        if short_k not in self.reference_stops:
            self.reference_stops[short_k] = entry

    def _lookup_postcode(self, postcode):
        """Look up a UK postcode via postcodes.io and return coordinates dict or None."""
        q = urllib.parse.quote(postcode.replace(' ', ''))
        url = f"https://api.postcodes.io/postcodes/{q}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'LibrariesHacked-Data/1.0'})
            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read().decode('utf-8'))
                if data.get('status') == 200 and data.get('result'):
                    r = data['result']
                    return {
                        'geox': round(r['longitude'], 5),
                        'geoy': round(r['latitude'], 5),
                        'postcode': r.get('postcode', postcode),
                        'source': 'postcodes.io'
                    }
        except Exception:
            pass
        return None

    def _lookup_place(self, community, authority):
        """Resolve a community via places_cache or postcodes.io places API filtered by authority."""
        cache_k = f"{normalise_key(authority)}::{normalise_key(community)}"
        if cache_k in self.places_cache:
            return self.places_cache[cache_k]

        q = urllib.parse.quote(community)
        url = f"https://api.postcodes.io/places?q={q}&limit=5"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'LibrariesHacked-Data/1.0'})
            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read().decode('utf-8'))
                results = data.get('result', [])
                match = None
                for r in results:
                    county = r.get('county_unitary') or ''
                    district = r.get('district_borough') or ''
                    if authority.lower() in county.lower() or authority.lower() in district.lower():
                        match = r
                        break
                if not match and results:
                    match = results[0]

                if match:
                    geo = {
                        'geox': round(match['longitude'], 5),
                        'geoy': round(match['latitude'], 5),
                        'postcode': '',
                        'source': 'places.io'
                    }
                    self.places_cache[cache_k] = geo
                    return geo
        except Exception:
            pass

        self.places_cache[cache_k] = None
        return None

    def _lookup_nominatim(self, stop, community, authority):
        """Geocode a stop via OpenStreetMap Nominatim and return coordinates dict or None."""
        query_str = f"{stop}, {community}, {authority}, UK".strip(', ')
        q = urllib.parse.quote(query_str)
        url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'LibrariesHacked-DataPipeline/1.0'})
            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read().decode('utf-8'))
                if data:
                    # Respect Nominatim's 1 request/second usage policy
                    time.sleep(1.0)
                    return {
                        'geox': round(float(data[0]['lon']), 5),
                        'geoy': round(float(data[0]['lat']), 5),
                        'postcode': '',
                        'source': 'nominatim'
                    }
        except Exception:
            pass
        return None
