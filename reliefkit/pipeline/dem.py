"""DEM fetch + prep. Sources (keyless):
  3dep10  USGS 3DEP 1/3 arc-second, via TNM Access API (US only)
  cop30   Copernicus GLO-30 DSM, AWS open data (global)
  cop90   Copernicus GLO-90, AWS open data (global, light)
Output: dem_utm.tif (Float32, UTM), heightmap_16.tif + .png (UInt16, frame px),
        returns dict(min, max, px_w, px_h).
"""
import json
import math
import os

from . import util
from .util import fetch, fetch_json, run, which_gdal

TNM = ("https://tnmaccess.nationalmap.gov/api/v1/products?datasets="
       "National%20Elevation%20Dataset%20(NED)%201/3%20arc-second"
       "&bbox={w},{s},{e},{n}&outputFormat=JSON&max=100")


def _cop_tiles(bbox, res):
    w, s, e, n = bbox
    names = []
    for lat in range(int(math.floor(s)), int(math.floor(n)) + 1):
        for lon in range(int(math.floor(w)), int(math.floor(e)) + 1):
            ns = "N%02d" % lat if lat >= 0 else "S%02d" % -lat
            ew = "E%03d" % lon if lon >= 0 else "W%03d" % -lon
            name = "Copernicus_DSM_COG_%s_%s_00_%s_00_DEM" % (res, ns, ew)
            names.append("https://copernicus-dem-%sm.s3.amazonaws.com/%s/%s.tif"
                         % ("30" if res == "10" else "90", name, name))
    return names


def _download(source, bbox, cache, log):
    files = []
    if source == "3dep10":
        w, s, e, n = bbox
        j = fetch_json(TNM.format(w=w, s=s, e=e, n=n), log=log)
        urls = sorted({it["downloadURL"] for it in j.get("items", [])
                       if it.get("downloadURL", "").endswith(".tif")})
        if not urls:
            raise RuntimeError("TNM returned no 3DEP tiles here; use cop30")
        for u in urls[:16]:
            files.append(fetch(u, os.path.join(cache, os.path.basename(u)), log=log))
    else:
        res = "10" if source == "cop30" else "30"
        for u in _cop_tiles(bbox, res):
            dest = os.path.join(cache, os.path.basename(u))
            try:
                files.append(fetch(u, dest, log=log))
            except Exception:
                log("no tile (ocean?) " + os.path.basename(u))
        if not files:
            raise RuntimeError("no Copernicus tiles intersect the box")
    return files


def build(job, page, log):
    d = job["dirs"]
    cache = os.path.join(util.CACHE, "dem", job["params"]["dem"])
    os.makedirs(cache, exist_ok=True)
    files = _download(job["params"]["dem"], page.bbox, cache, log)

    vrt = os.path.join(d["data"], "dem.vrt")
    run([which_gdal("gdalbuildvrt"), vrt] + files, log)

    px_w, px_h = page.frame_px(dpi=job["params"].get("dpi", 300))
    px_w, px_h = min(px_w, 4200), min(px_h, 4200)
    dem_utm = os.path.join(d["data"], "dem_utm.tif")
    run([which_gdal("gdalwarp"), "-overwrite", "-t_srs", "EPSG:%d" % page.epsg,
         "-te", page.x0, page.y0, page.x1, page.y1, "-ts", px_w, px_h,
         "-r", "cubic", "-ot", "Float32", "-dstnodata", "0", vrt, dem_utm], log)

    info = json.loads(run([which_gdal("gdalinfo"), "-json", "-stats", dem_utm], log).stdout)
    b = info["bands"][0]
    zmin = b.get("minimum", 0.0)
    zmax = b.get("maximum", 1.0)
    if zmax - zmin < 1:
        zmax = zmin + 1

    hm16 = os.path.join(d["relief"], "heightmap_16.tif")
    run([which_gdal("gdal_translate"), "-ot", "UInt16",
         "-scale", zmin, zmax, 0, 65535, dem_utm, hm16], log)
    hm_png = os.path.join(d["relief"], "heightmap_16.png")
    run([which_gdal("gdal_translate"), "-of", "PNG", hm16, hm_png], log)

    meta = {"min": zmin, "max": zmax, "px_w": px_w, "px_h": px_h,
            "m_per_px": (page.x1 - page.x0) / px_w}
    log("DEM %dx%d px, %.0f..%.0f m" % (px_w, px_h, zmin, zmax))
    return meta
