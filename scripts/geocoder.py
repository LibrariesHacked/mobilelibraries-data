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


def normalise_key(text):
    if not text:
        return ''
    return re.sub(r'[^a-z0-9]', '', str(text).lower())


class Geocoder:
    def __init__(self):
        self.reference_stops = {}
        self.places_cache = {}
        self._load_caches()

    def _load_caches(self):
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

    def save_caches(self):
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

        # 1. Match full reference key
        full_k = f"{auth_k}::{comm_k}::{stop_k}"
        if full_k in self.reference_stops:
            entry = self.reference_stops[full_k]
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
            return {
                'geox': entry['geox'],
                'geoy': entry['geoy'],
                'postcode': entry.get('postcode') or postcode,
                'source': f"ref_cache_short:{entry.get('source', 'known')}"
            }

        # 3. Postcode lookup if valid full UK postcode
        clean_pc = postcode.strip().upper()
        if clean_pc and len(clean_pc.split()) == 2:
            geo = self._lookup_postcode(clean_pc)
            if geo:
                self.remember_stop(authority, community, stop, geo['geox'], geo['geoy'], clean_pc, 'postcode_api')
                return geo

        # 4. Lookup community/village in places cache or API
        if community:
            place_geo = self._lookup_place(community, authority)
            if place_geo:
                self.remember_stop(authority, community, stop, place_geo['geox'], place_geo['geoy'], place_geo.get('postcode', ''), 'place_api')
                return place_geo

        # 5. Fallback Nominatim lookup using address + authority
        nom_geo = self._lookup_nominatim(stop, community, authority)
        if nom_geo:
            self.remember_stop(authority, community, stop, nom_geo['geox'], nom_geo['geoy'], nom_geo.get('postcode', ''), 'nominatim')
            return nom_geo

        return {'geox': '', 'geoy': '', 'postcode': clean_pc, 'source': 'none'}

    def remember_stop(self, authority, community, stop, geox, geoy, postcode='', source='runtime'):
        auth_k = normalise_key(authority)
        comm_k = normalise_key(community)
        stop_k = normalise_key(stop)

        entry = {
            'authority': authority,
            'community': community,
            'stop': stop,
            'postcode': postcode,
            'geox': round(float(geox), 6),
            'geoy': round(float(geoy), 6),
            'source': source
        }

        full_k = f"{auth_k}::{comm_k}::{stop_k}"
        short_k = f"{auth_k}::{stop_k}"
        self.reference_stops[full_k] = entry
        if short_k not in self.reference_stops:
            self.reference_stops[short_k] = entry

    def _lookup_postcode(self, postcode):
        q = urllib.parse.quote(postcode.replace(' ', ''))
        url = f"https://api.postcodes.io/postcodes/{q}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'LibrariesHacked-Data/1.0'})
            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read().decode('utf-8'))
                if data.get('status') == 200 and data.get('result'):
                    r = data['result']
                    return {
                        'geox': round(r['longitude'], 6),
                        'geoy': round(r['latitude'], 6),
                        'postcode': r.get('postcode', postcode),
                        'source': 'postcodes.io'
                    }
        except Exception:
            pass
        return None

    def _lookup_place(self, community, authority):
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
                        'geox': round(match['longitude'], 6),
                        'geoy': round(match['latitude'], 6),
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
        query_str = f"{stop}, {community}, {authority}, UK".strip(', ')
        q = urllib.parse.quote(query_str)
        url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'LibrariesHacked-DataPipeline/1.0'})
            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read().decode('utf-8'))
                if data:
                    time.sleep(1.0)
                    return {
                        'geox': round(float(data[0]['lon']), 6),
                        'geoy': round(float(data[0]['lat']), 6),
                        'postcode': '',
                        'source': 'nominatim'
                    }
        except Exception:
            pass
        return None
