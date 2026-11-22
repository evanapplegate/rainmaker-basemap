"""Vector fetchers: TIGER prisec roads, OSM (roads, water, places, peaks,
rivers, camps, parking), PAD-US ownership. Everything lands as GeoJSON in
lon/lat; svgout does the projection."""
import json
import os
import urllib.parse
import zipfile

from . import util
from .util import fetch, fetch_json, run, which_gdal

STATES_CARTO = ("https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_20m.zip")
TIGER_PRISEC = ("https://www2.census.gov/geo/tiger/TIGER2024/PRISECROADS/"
                "tl_2024_{fips}_prisecroads.zip")
OVERPASS = "https://overpass-api.de/api/interpreter"
PADUS = ("https://services.arcgis.com/v01gqwM5QqNysAAi/ArcGIS/rest/services/"
         "Manager_Name/FeatureServer/0/query")


# ------------------------------------------------------------------ helpers
def _states_geojson(log):
    cache = os.path.join(util.CACHE, "census")
    os.makedirs(cache, exist_ok=True)
    gj = os.path.join(cache, "states_20m.geojson")
    if not os.path.exists(gj):
        z = fetch(STATES_CARTO, os.path.join(cache, "states.zip"), log=log)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(os.path.join(cache, "states"))
        shp = [f for f in os.listdir(os.path.join(cache, "states")) if f.endswith(".shp")][0]
        run([which_gdal("ogr2ogr"), "-f", "GeoJSON", gj,
             os.path.join(cache, "states", shp)], log)
    with open(gj, encoding="utf-8") as f:
        return json.load(f)


def _bbox_hits_poly(bbox, geom):
    w, s, e, n = bbox

    def ring_hit(ring):
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return not (max(xs) < w or min(xs) > e or max(ys) < s or min(ys) > n)

    if geom["type"] == "Polygon":
        return ring_hit(geom["coordinates"][0])
    if geom["type"] == "MultiPolygon":
        return any(ring_hit(p[0]) for p in geom["coordinates"])
    return False


# ------------------------------------------------------------------ TIGER
def tiger_roads(job, page, log):
    """Freeway / primary / secondary from Census PRISECROADS, clipped."""
    d = job["dirs"]
    bbox = page.bbox
    states = _states_geojson(log)
    fips = [ft["properties"]["STATEFP"] for ft in states["features"]
            if _bbox_hits_poly(bbox, ft["geometry"])]
    if not fips:
        log("bbox outside the US; skipping TIGER roads")
        return None
    cache = os.path.join(util.CACHE, "tiger")
    os.makedirs(cache, exist_ok=True)
    parts = []
    for fp in fips[:6]:
        url = TIGER_PRISEC.format(fips=fp)
        z = fetch(url, os.path.join(cache, os.path.basename(url)), log=log)
        ext = os.path.join(cache, "prisec_" + fp)
        if not os.path.isdir(ext):
            with zipfile.ZipFile(z) as zf:
                zf.extractall(ext)
        shp = [f for f in os.listdir(ext) if f.endswith(".shp")][0]
        parts.append(os.path.join(ext, shp))
    out = os.path.join(d["data"], "roads_tiger.geojson")
    if os.path.exists(out):
        os.remove(out)
    w, s, e, n = bbox
    for i, shp in enumerate(parts):
        run([which_gdal("ogr2ogr"), "-f", "GeoJSON",
             "-clipsrc", w, s, e, n] +
            (["-append"] if i else []) + [out, shp], log)
    return out


# ------------------------------------------------------------------ OSM
OSM_QUERY = """
[out:json][timeout:120];
(
  way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|track)$"]({s},{w},{n},{e});
  way["waterway"~"^(river|stream|canal)$"]({s},{w},{n},{e});
  way["natural"="water"]({s},{w},{n},{e});
  relation["natural"="water"]({s},{w},{n},{e});
  node["place"~"^(city|town|village|hamlet|locality)$"]({s},{w},{n},{e});
  node["natural"="peak"]({s},{w},{n},{e});
  node["tourism"="camp_site"]({s},{w},{n},{e});
  node["amenity"="parking"]["access"!="private"]({s},{w},{n},{e});
  node["highway"="trailhead"]({s},{w},{n},{e});
);
out body geom 60000;
"""


def osm(job, page, log):
    d = job["dirs"]
    w, s, e, n = page.bbox
    q = OSM_QUERY.format(w=w, s=s, e=e, n=n)
    out = os.path.join(d["data"], "osm.json")
    if not os.path.exists(out):
        log("Overpass query (roads, water, places, peaks, camps)...")
        data = urllib.parse.urlencode({"data": q}).encode()
        j = fetch_json(OVERPASS, log=log, post=data)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(j, f)
    with open(out, encoding="utf-8") as f:
        j = json.load(f)
    log("OSM elements: %d" % len(j.get("elements", [])))
    return j


# ------------------------------------------------------------------ PAD-US
MANG_CLASS = {  # Mang_Name -> (legend label, fill)
    "BLM": ("BLM", "#efe4c8"),
    "USFS": ("US Forest Service", "#dde7cf"),
    "NPS": ("National Park Service", "#dce7d2"),
    "FWS": ("US Fish & Wildlife", "#d8e4d8"),
    "DOD": ("Military", "#e4dcd4"),
    "ST": ("State", "#e3e9d6"),
    "SPR": ("State Parks", "#dbe8d4"),
    "SDNR": ("State DNR", "#e3e9d6"),
    "CNTY": ("County", "#e9e6da"),
    "CITY": ("City", "#e9e6da"),
    "TRIB": ("Tribal", "#ece2cf"),
}


def padus(job, page, log):
    d = job["dirs"]
    w, s, e, n = page.bbox
    feats = []
    offset = 0
    while True:
        params = {
            "geometry": json.dumps({"xmin": w, "ymin": s, "xmax": e, "ymax": n,
                                    "spatialReference": {"wkid": 4326}}),
            "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "Mang_Name,Mang_Type,Unit_Nm",
            "outSR": 4326, "f": "geojson",
            "resultOffset": offset, "resultRecordCount": 1000,
            "where": "1=1",
        }
        url = PADUS + "?" + urllib.parse.urlencode(params)
        try:
            j = fetch_json(url, log=log)
        except Exception as ex:
            log("PAD-US fetch failed (%s); skipping ownership" % ex)
            return None
        fs = j.get("features", [])
        feats.extend(fs)
        if len(fs) < 1000 or offset > 8000:
            break
        offset += 1000
    out = os.path.join(d["data"], "padus.geojson")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)
    log("PAD-US polygons: %d" % len(feats))
    return out
