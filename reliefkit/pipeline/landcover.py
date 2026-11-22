"""Landcover: ESA WorldCover 10 m v200 (2021) from the AWS open bucket,
reclassed to the ReliefKit tint palette with gdaldem color-relief.
Classes: 10 tree, 20 shrub, 30 grass, 40 crop, 50 built, 60 bare, 70 snow,
80 water, 90 wetland, 95 mangrove, 100 moss."""
import math
import os

from . import util
from .util import fetch, run, which_gdal

BUCKET = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"

# gentle Raven-ish tints: quiet greens, warm neutrals, no shouting
PALETTE = {
    10: (201, 216, 188),   # tree cover        soft green
    20: (222, 226, 203),   # shrubland         sage
    30: (228, 231, 207),   # grassland         pale green-cream
    40: (235, 231, 204),   # cropland          warm straw
    50: (226, 220, 212),   # built-up          warm grey
    60: (233, 228, 214),   # bare / sparse     light tan
    70: (248, 250, 250),   # snow / ice        near-white
    80: (205, 222, 229),   # water             quiet blue
    90: (210, 225, 212),   # wetland           grey-green
    95: (199, 219, 203),   # mangrove
    100: (226, 228, 210),  # moss / lichen
    0: (236, 232, 219),    # nodata -> paper
}


def _tiles(bbox):
    w, s, e, n = bbox
    lat0 = int(math.floor(s / 3.0) * 3)
    lon0 = int(math.floor(w / 3.0) * 3)
    out = []
    lat = lat0
    while lat <= n:
        lon = lon0
        while lon <= e:
            ns = "N%02d" % lat if lat >= 0 else "S%02d" % -lat
            ew = "E%03d" % lon if lon >= 0 else "W%03d" % -lon
            out.append("%s/ESA_WorldCover_10m_2021_v200_%s%s_Map.tif" % (BUCKET, ns, ew))
            lon += 3
        lat += 3
    return out


def build(job, page, dem_meta, log):
    d = job["dirs"]
    cache = os.path.join(util.CACHE, "worldcover")
    os.makedirs(cache, exist_ok=True)
    files = []
    for u in _tiles(page.bbox):
        try:
            files.append(fetch(u, os.path.join(cache, os.path.basename(u)), log=log))
        except Exception:
            log("no landcover tile " + os.path.basename(u))
    if not files:
        raise RuntimeError("no WorldCover tiles found")

    vrt = os.path.join(d["data"], "landcover.vrt")
    run([which_gdal("gdalbuildvrt"), vrt] + files, log)
    lc_utm = os.path.join(d["data"], "landcover_utm.tif")
    run([which_gdal("gdalwarp"), "-overwrite", "-t_srs", "EPSG:%d" % page.epsg,
         "-te", page.x0, page.y0, page.x1, page.y1,
         "-ts", dem_meta["px_w"], dem_meta["px_h"], "-r", "mode", vrt, lc_utm], log)

    ramp = os.path.join(d["data"], "lc_palette.txt")
    with open(ramp, "w") as f:
        for v, (r, g, b) in sorted(PALETTE.items()):
            f.write("%d %d %d %d\n" % (v, r, g, b))
    tint = os.path.join(d["relief"], "landcover_tint.tif")
    run([which_gdal("gdaldem"), "color-relief", lc_utm, ramp, tint,
         "-exact_color_entry"], log)
    log("landcover tint ready")
    return tint
