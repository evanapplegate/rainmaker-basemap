"""Job orchestrator: params in, assets + Adobe scripts out."""
import json
import os
import platform
import re
import subprocess
import time

from . import contours, dem, landcover, relief, svgout, vectors, util

JSX_DIR = os.path.join(util.ROOT, "jsx")


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "map").lower()).strip("-") or "map"


def run_job(params, log):
    t0 = time.time()
    name = _slug(params.get("title")) + time.strftime("-%m%d-%H%M")
    jdir = os.path.join(util.JOBS, name)
    dirs = {k: os.path.join(jdir, k) for k in ("data", "relief", "svg", "psd", "ai")}
    for p in dirs.values():
        os.makedirs(p, exist_ok=True)
    job = {"name": name, "dir": jdir, "dirs": dirs, "params": params}
    layers = params.get("layers", {})

    def on(key):
        return layers.get(key, True)

    page = util.Page(params["page"], params["bbox"])
    log("page %s, frame %.0fx%.0fpt, 1:%s, UTM EPSG:%d"
        % (params["page"], page.fw, page.fh, "{:,}".format(int(page.scale)), page.epsg))

    log("== DEM ==")
    dem_meta = dem.build(job, page, log)

    tint = None
    if on("landcover"):
        log("== landcover ==")
        tint = landcover.build(job, page, dem_meta, log)

    log("== relief: GDAL multidirectional ==")
    relief.gdal_relief(job, dem_meta, log)
    bl = None
    if on("relief_blender"):
        log("== relief: Blender ==")
        bl = relief.blender_relief(job, dem_meta, log)

    if on("contours"):
        log("== contours ==")
        contours.build(job, page, log)
        svgout.contour_svgs(job, page, log)

    log("== OSM ==")
    osm_json = vectors.osm(job, page, log)
    if on("water"):
        svgout.water_svgs(job, page, osm_json, log)

    road_refs = {}
    if on("roads"):
        log("== roads ==")
        vectors.tiger_roads(job, page, log)
        _, road_refs = svgout.roads_svgs(job, page, osm_json, log)
    if on("shields") and road_refs:
        svgout.shields_svg(job, page, road_refs, log)

    if on("ownership"):
        log("== PAD-US ownership ==")
        vectors.padus(job, page, log)
        svgout.ownership_svg(job, page, log)

    if on("labels"):
        log("== labels ==")
        svgout.labels_svg(job, page, osm_json, log)

    if on("locator"):
        svgout.locator_svg(job, page, log)
    svgout.frame_svg(job, page, log)

    manifest = {
        "name": name, "params": params, "page_pt": [page.w, page.h],
        "frame_pt": list(page.frame), "epsg": page.epsg,
        "scale": int(page.scale), "dem": dem_meta,
        "blender_relief": bool(bl), "created": time.strftime("%Y-%m-%d %H:%M"),
    }
    with open(os.path.join(jdir, "job.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)

    log("== Adobe assembly ==")
    adobe = assemble_adobe(job, manifest, log)
    log("done in %.1f min  ->  %s" % ((time.time() - t0) / 60, jdir))
    return {"dir": jdir, "adobe": adobe, "manifest": manifest}


def _gen_jsx(job, manifest, template, out_name):
    with open(template, encoding="utf-8") as f:
        body = f.read()
    cfg = "var JOB = " + json.dumps({
        "dir": job["dir"].replace("\\", "/"),
        "name": job["name"],
        "page": manifest["page_pt"], "frame": manifest["frame_pt"],
        "blender": manifest["blender_relief"],
        "layers": job["params"].get("layers", {}),
    }) + ";\n"
    out = os.path.join(job["dir"], out_name)
    with open(out, "w", encoding="utf-8") as f:
        f.write(cfg + body)
    return out


def assemble_adobe(job, manifest, log):
    ps_jsx = _gen_jsx(job, manifest, os.path.join(JSX_DIR, "build_psd.jsx"), "build_psd.gen.jsx")
    ai_jsx = _gen_jsx(job, manifest, os.path.join(JSX_DIR, "build_ai.jsx"), "build_ai.gen.jsx")
    if platform.system() != "Darwin":
        log("not macOS: run the two .jsx files in Photoshop then Illustrator by hand")
        log("  " + ps_jsx)
        log("  " + ai_jsx)
        return "scripts-only"
    ok = True
    for app, jsx in (("com.adobe.photoshop", ps_jsx), ("com.adobe.illustrator", ai_jsx)):
        osa = ('tell application id "%s"\nactivate\ndo javascript (POSIX file "%s")\nend tell'
               % (app, jsx))
        log("driving %s..." % app.split(".")[-1])
        r = subprocess.run(["osascript", "-e", osa], capture_output=True, text=True)
        if r.returncode != 0:
            ok = False
            log("  %s failed: %s" % (app, r.stderr.strip()[:400]))
            log("  open %s manually (File > Scripts)" % jsx)
        else:
            log("  ok " + (r.stdout.strip()[:200] or ""))
    return "assembled" if ok else "partial"
