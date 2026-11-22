"""Two reliefs from one DEM:
  relief_gdal.tif     gdaldem -multidirectional, softened with a slope veil
  relief_blender.tif  Cycles render of a displaced plane (somethingaboutmaps-style)
Both greyscale, same pixel grid as the DEM."""
import os
import subprocess

from .util import blender_path, run, which_gdal

BL_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bl_scene.py")


def gdal_relief(job, dem_meta, log):
    d = job["dirs"]
    dem = os.path.join(d["data"], "dem_utm.tif")
    hs = os.path.join(d["relief"], "relief_gdal.tif")
    run([which_gdal("gdaldem"), "hillshade", "-multidirectional", "-compute_edges",
         "-z", 1.3 if job["params"]["texture"] == "high" else 1.0,
         dem, hs], log)
    return hs


def blender_relief(job, dem_meta, log):
    bl = blender_path()
    if not bl:
        log("Blender not found; skipping Blender relief")
        return None
    d = job["dirs"]
    hm = os.path.join(d["relief"], "heightmap_16.png")
    out = os.path.join(d["relief"], "relief_blender")
    # vertical scale: real-world exaggeration mapped into plane units
    zrange = dem_meta["max"] - dem_meta["min"]
    width_m = dem_meta["m_per_px"] * dem_meta["px_w"]
    ex = 1.6 if job["params"]["texture"] == "high" else 1.0
    disp = (zrange / width_m) * 2.0 * ex   # plane is 2 units wide
    cmd = [bl, "-b", "--factory-startup", "-noaudio", "-P", BL_SCRIPT, "--",
           hm, out, "%d" % dem_meta["px_w"], "%d" % dem_meta["px_h"],
           "%.6f" % disp, job["params"]["texture"]]
    log("$ blender headless render (this is the slow part)")
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    tail = (r.stdout + r.stderr)[-1500:]
    log(tail)
    png = out + ".png"
    if not os.path.exists(png):
        log("Blender render failed; GDAL relief still available")
        return None
    tif = os.path.join(d["relief"], "relief_blender.tif")
    run([which_gdal("gdal_translate"), png, tif], log)
    return tif
