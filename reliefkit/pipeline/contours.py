"""Contours from the UTM DEM via gdal_contour. Index contours every 5th line.
Returns geojson path (UTM coords; svgout projects them to page)."""
import json
import os

from .util import run, which_gdal


def build(job, page, log):
    d = job["dirs"]
    interval = float(job["params"]["contour_interval"])
    dem = os.path.join(d["data"], "dem_utm.tif")
    gj = os.path.join(d["data"], "contours.geojson")
    if os.path.exists(gj):
        os.remove(gj)
    run([which_gdal("gdal_contour"), "-a", "elev", "-i", interval, dem, gj,
         "-f", "GeoJSON"], log)
    with open(gj, encoding="utf-8") as f:
        fc = json.load(f)
    idx = interval * 5
    for ft in fc["features"]:
        e = ft["properties"].get("elev", 0)
        ft["properties"]["index"] = 1 if abs(e % idx) < 1e-6 else 0
    with open(gj, "w", encoding="utf-8") as f:
        json.dump(fc, f)
    log("contours: %d lines at %gm (index every %gm)" % (len(fc["features"]), interval, idx))
    return gj
