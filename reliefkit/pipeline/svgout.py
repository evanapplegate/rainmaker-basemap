"""Turns fetched vectors into one SVG per Illustrator layer, in page points.
Also builds the locator, frame and metadata strip. Fonts reference the
Rainmaker families by PostScript-ish names; build_ai.jsx maps them again."""
import json
import math
import os

from . import util
from .util import SVG, fetch, run, which_gdal
from .vectors import MANG_CLASS

FG = "TestFoundersGroteskText-Regular"
FG_MED = "TestFoundersGroteskText-Medium"
FG_SEMI = "TestFoundersGroteskText-Semibold"
FLECHA_BI = "FlechaTestS-BoldItalic"

INK = "#3f3a33"
PAPER = "#f3efe4"
CONTOUR_BROWN = "#9a7352"
WATER_BLUE = "#7fa8bd"
WATER_FILL = "#cddde5"


# ------------------------------------------------------------------ geometry
def _lines(geom):
    t = geom["type"]
    if t == "LineString":
        return [geom["coordinates"]]
    if t == "MultiLineString":
        return geom["coordinates"]
    return []


def _polys(geom):
    t = geom["type"]
    if t == "Polygon":
        return [geom["coordinates"]]
    if t == "MultiPolygon":
        return geom["coordinates"]
    return []


def _pt_path(page, coords):
    return [page.to_pt(c[0], c[1]) for c in coords]


def _path_len(pts):
    return sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
               for i in range(len(pts) - 1))


def _point_at(pts, dist):
    """(x, y, angle_deg) at distance along a pt polyline."""
    acc = 0
    for i in range(len(pts) - 1):
        seg = math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        if acc + seg >= dist and seg > 0:
            t = (dist - acc) / seg
            x = pts[i][0] + t * (pts[i + 1][0] - pts[i][0])
            y = pts[i][1] + t * (pts[i + 1][1] - pts[i][1])
            a = math.degrees(math.atan2(pts[i + 1][1] - pts[i][1],
                                        pts[i + 1][0] - pts[i][0]))
            if a > 90:
                a -= 180
            if a < -90:
                a += 180
            return x, y, a
        acc += seg
    return pts[-1][0], pts[-1][1], 0


def _in_frame(page, x, y, pad=0):
    fx0, fy0, fx1, fy1 = page.frame
    return fx0 - pad <= x <= fx1 + pad and fy0 - pad <= y <= fy1 + pad


# ------------------------------------------------------------------ contours
def contour_svgs(job, page, log):
    """Lines layer + labels layer. The AI script merges labels into a knockout
    group over the lines (somethingaboutmaps halo-knockout technique)."""
    d = job["dirs"]
    gj = os.path.join(d["data"], "contours.geojson")
    # contours were generated in UTM; project UTM->pt directly
    with open(gj, encoding="utf-8") as f:
        fc = json.load(f)

    def utm_to_pt(x, y):
        fx0, fy0, fx1, fy1 = page.frame
        px = fx0 + (x - page.x0) / (page.x1 - page.x0) * page.fw
        py = fy0 + (1 - (y - page.y0) / (page.y1 - page.y0)) * page.fh
        return px, py

    lines = SVG(page)
    labels = SVG(page)
    n_lab = 0
    for ft in fc["features"]:
        idx = ft["properties"].get("index")
        elev = ft["properties"].get("elev", 0)
        for coords in _lines(ft["geometry"]):
            pts = [utm_to_pt(c[0], c[1]) for c in coords]
            if len(pts) < 2:
                continue
            lines.path(pts, stroke=CONTOUR_BROWN, width=0.6 if idx else 0.25,
                       opacity=0.75 if idx else 0.55)
            if idx and n_lab < 160:
                L = _path_len(pts)
                if L > 140:
                    step = max(260.0, L / 3)
                    dist = step / 2
                    while dist < L:
                        x, y, a = _point_at(pts, dist)
                        if _in_frame(page, x, y, -8):
                            labels.text(x, y + 1.6, "%d" % round(elev), size=4.6,
                                        font=FG, fill=CONTOUR_BROWN,
                                        anchor="middle", angle=a)
                            n_lab += 1
                        dist += step
    p1 = lines.save(os.path.join(d["svg"], "contours.svg"))
    p2 = labels.save(os.path.join(d["svg"], "contour_labels.svg"))
    log("contour svg + %d labels" % n_lab)
    return p1, p2


# ------------------------------------------------------------------ water
def water_svgs(job, page, osm_json, log):
    d = job["dirs"]
    fills = SVG(page)
    lines = SVG(page)
    for el in osm_json.get("elements", []):
        tags = el.get("tags", {})
        if el["type"] == "way" and "geometry" in el:
            coords = [(g["lon"], g["lat"]) for g in el["geometry"]]
            if tags.get("natural") == "water":
                fills.poly([_pt_path(page, coords)], WATER_FILL)
            elif tags.get("waterway") in ("river", "stream", "canal"):
                wd = {"river": 1.1, "stream": 0.45, "canal": 0.6}[tags["waterway"]]
                dash = None if tags.get("intermittent") != "yes" else "3,1.6"
                lines.path(_pt_path(page, coords), stroke=WATER_BLUE, width=wd, dash=dash)
    p1 = fills.save(os.path.join(d["svg"], "water_fill.svg"))
    p2 = lines.save(os.path.join(d["svg"], "water_lines.svg"))
    return p1, p2


# ------------------------------------------------------------------ ownership
def ownership_svg(job, page, log):
    d = job["dirs"]
    gj = os.path.join(d["data"], "padus.geojson")
    if not os.path.exists(gj):
        return None
    with open(gj, encoding="utf-8") as f:
        fc = json.load(f)
    svg = SVG(page)
    seen = {}
    for ft in fc["features"]:
        mang = (ft["properties"] or {}).get("Mang_Name", "")
        cls = MANG_CLASS.get(mang)
        if not cls:
            continue
        label, fill = cls
        seen[label] = fill
        for rings in _polys(ft["geometry"]):
            svg.poly([_pt_path(page, r) for r in rings], fill, opacity=0.35)
    p = svg.save(os.path.join(d["svg"], "ownership.svg"))
    job["legend_ownership"] = seen
    log("ownership classes: %s" % ", ".join(sorted(seen)) if seen else "ownership: none here")
    return p


# ------------------------------------------------------------------ roads
ROAD_STYLE = {   # class -> (casing_w, fill_w, fill_color)
    "interstate": (2.6, 1.7, "#ffffff"),
    "us":         (2.1, 1.3, "#ffffff"),
    "state":      (1.7, 1.0, "#ffffff"),
    "major":      (1.4, 0.8, "#ffffff"),
    "minor":      (0.9, 0.5, "#ffffff"),
    "track":      (0.0, 0.5, None),
}


def _tiger_class(props):
    rt = (props.get("RTTYP") or "").strip()
    if rt == "I":
        return "interstate"
    if rt == "U":
        return "us"
    if rt == "S":
        return "state"
    return "major"


def _osm_class(tags):
    h = tags.get("highway", "")
    if h in ("motorway", "trunk"):
        return "major"
    if h in ("primary", "secondary"):
        return "major"
    if h in ("tertiary", "unclassified", "residential"):
        return "minor"
    if h == "track":
        return "track"
    return None


def roads_svgs(job, page, osm_json, log):
    """One SVG per road class, casing + fill as separate saved files so the AI
    script can give each class its own cased sublayer pair."""
    d = job["dirs"]
    byclass = {k: [] for k in ROAD_STYLE}
    refs = {}  # (shield_kind, number) -> longest pts

    tgj = os.path.join(d["data"], "roads_tiger.geojson")
    have_tiger = os.path.exists(tgj)
    if have_tiger:
        with open(tgj, encoding="utf-8") as f:
            for ft in json.load(f)["features"]:
                cls = _tiger_class(ft["properties"] or {})
                for coords in _lines(ft["geometry"]):
                    pts = _pt_path(page, coords)
                    byclass[cls].append(pts)
                    name = (ft["properties"] or {}).get("FULLNAME") or ""
                    rt = (ft["properties"] or {}).get("RTTYP")
                    num = "".join(ch for ch in name if ch.isdigit())
                    if rt in ("I", "U", "S") and num:
                        kind = {"I": "interstate", "U": "us", "S": "state"}[rt]
                        key = (kind, num)
                        if key not in refs or _path_len(pts) > _path_len(refs[key]):
                            refs[key] = pts

    for el in osm_json.get("elements", []):
        tags = el.get("tags", {})
        if el["type"] != "way" or "geometry" not in el:
            continue
        cls = _osm_class(tags)
        if not cls:
            continue
        if have_tiger and cls == "major" and tags.get("highway") in (
                "motorway", "trunk", "primary", "secondary"):
            continue  # TIGER already covers prisec in the US
        pts = _pt_path(page, [(g["lon"], g["lat"]) for g in el["geometry"]])
        byclass[cls].append(pts)
        ref = tags.get("ref", "")
        if not have_tiger and ref and tags.get("highway") in ("motorway", "trunk", "primary"):
            num = "".join(ch for ch in ref if ch.isdigit())
            kind = "interstate" if ref.upper().startswith("I") else "state"
            if num:
                key = (kind, num)
                if key not in refs or _path_len(pts) > _path_len(refs[key]):
                    refs[key] = pts

    out = {}
    for cls, (cw, fw, fcol) in ROAD_STYLE.items():
        if not byclass[cls]:
            continue
        casing = SVG(page)
        fill = SVG(page)
        for pts in byclass[cls]:
            if cw:
                casing.path(pts, stroke="#6d675c", width=cw)
            if cls == "track":
                fill.path(pts, stroke="#7a7265", width=fw, dash="2.4,1.2", cap="butt")
            else:
                fill.path(pts, stroke=fcol or "#fff", width=fw)
        paths = []
        if cw:
            paths.append(casing.save(os.path.join(d["svg"], "roads_%s_casing.svg" % cls)))
        paths.append(fill.save(os.path.join(d["svg"], "roads_%s_fill.svg" % cls)))
        out[cls] = paths
    log("road classes: %s" % ", ".join(sorted(out)))
    return out, refs


# ------------------------------------------------------------------ shields
def shields_svg(job, page, refs, log):
    """Simplified mono shields: shape encodes the system, no color."""
    d = job["dirs"]
    svg = SVG(page)
    placed = 0
    used = []
    for (kind, num), pts in sorted(refs.items(), key=lambda kv: -_path_len(kv[1])):
        if placed >= 14:
            break
        x, y, _ = _point_at(pts, _path_len(pts) * 0.5)
        if not _in_frame(page, x, y, -14):
            continue
        if any(math.hypot(x - ux, y - uy) < 46 for ux, uy in used):
            continue
        used.append((x, y))
        r = 7.2 if len(num) < 3 else 8.4
        if kind == "interstate":
            svg.raw('<path d="M%.1f %.1f c %.1f %.1f %.1f %.1f %.1f 0 c %.1f %.1f %.1f %.1f %.1f %.1f '
                    'c %.1f %.1f %.1f %.1f %.1f %.1f c %.1f %.1f %.1f %.1f %.1f %.1f Z" '
                    'fill="#ffffff" stroke="#3f3a33" stroke-width="0.7"/>' % (
                        x - r, y - r * 0.72,
                        r * 0.6, r * 0.5, 2 * r - r * 0.6, r * 0.5, 2 * r,
                        0.15 * r, 0.8 * r, 0.1 * r, 1.45 * r, -0.4 * r, 1.72 * r,
                        -0.5 * r, 0.25 * r, -1.1 * r, 0.42 * r, -1.6 * r, 0.52 * r,
                        -0.5 * r, -0.1 * r, -1.35 * r, -0.27 * r, -1.6 * r, -0.52 * r,
                    ))
        elif kind == "us":
            svg.raw('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%.1f" '
                    'fill="#ffffff" stroke="#3f3a33" stroke-width="0.7"/>' % (
                        x - r, y - r * 0.85, 2 * r, 1.7 * r, r * 0.8))
        else:
            svg.raw('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#ffffff" '
                    'stroke="#3f3a33" stroke-width="0.7"/>' % (x, y, r * 0.95))
        svg.text(x, y + 2.3, num, size=6.4, font=FG_SEMI, fill=INK)
        placed += 1
    p = svg.save(os.path.join(d["svg"], "shields.svg"))
    log("shields placed: %d" % placed)
    return p


# ------------------------------------------------------------------ labels
def labels_svg(job, page, osm_json, log):
    d = job["dirs"]
    svg = SVG(page)
    pts_used = []

    def ok(x, y, sep):
        if not _in_frame(page, x, y, -10):
            return False
        if any(math.hypot(x - a, y - b) < sep for a, b in pts_used):
            return False
        pts_used.append((x, y))
        return True

    places, peaks, camps, parks_n, rivers = [], [], [], [], {}
    for el in osm_json.get("elements", []):
        tags = el.get("tags", {})
        if el["type"] == "node":
            if tags.get("place") in ("city", "town", "village", "hamlet", "locality") and tags.get("name"):
                places.append((tags["place"], tags["name"], el["lon"], el["lat"]))
            elif tags.get("natural") == "peak" and tags.get("name"):
                peaks.append((tags["name"], tags.get("ele"), el["lon"], el["lat"]))
            elif tags.get("tourism") == "camp_site":
                camps.append((tags.get("name", ""), el["lon"], el["lat"]))
            elif tags.get("amenity") == "parking" or tags.get("highway") == "trailhead":
                parks_n.append((tags.get("name", ""), el["lon"], el["lat"]))
        elif el["type"] == "way" and tags.get("waterway") in ("river", "stream") and tags.get("name"):
            pts = _pt_path(page, [(g["lon"], g["lat"]) for g in el["geometry"]])
            L = _path_len(pts)
            nm = tags["name"]
            if nm not in rivers or L > rivers[nm][0]:
                rivers[nm] = (L, pts)

    order = {"city": 0, "town": 1, "village": 2, "hamlet": 3, "locality": 4}
    places.sort(key=lambda p: order.get(p[0], 9))
    for kind, name, lon, lat in places[:40]:
        x, y = page.to_pt(lon, lat)
        size = {"city": 11, "town": 9, "village": 7.5, "hamlet": 6.5, "locality": 6}[kind]
        if not ok(x, y, size * 3.2):
            continue
        font = FG_MED if kind in ("city", "town") else FG
        svg.raw('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s"/>' % (x, y, 1.3 if kind in ("city", "town") else 1.0, INK))
        svg.text(x + 3.4, y + size * 0.34, name, size=size, font=font, fill=INK, anchor="start")

    for name, ele, lon, lat in peaks[:30]:
        x, y = page.to_pt(lon, lat)
        if not ok(x, y, 26):
            continue
        svg.raw('<path d="M%.1f %.1f L%.1f %.1f L%.1f %.1f Z" fill="%s"/>' % (
            x - 2.2, y + 1.6, x, y - 2.2, x + 2.2, y + 1.6, "#5d564c"))
        t = name if not ele else "%s %s" % (name, _ele_txt(ele))
        svg.text(x, y - 4.2, t, size=6.2, font=FG_MED, fill="#4a443c")

    for name, lon, lat in camps[:25]:
        x, y = page.to_pt(lon, lat)
        if not ok(x, y, 18):
            continue
        svg.raw('<path d="M%.1f %.1f L%.1f %.1f L%.1f %.1f Z" fill="none" stroke="#4e5d3a" stroke-width="0.9"/>'
                % (x - 3, y + 2.4, x, y - 2.8, x + 3, y + 2.4))
        if name:
            svg.text(x, y + 8.2, name, size=5.4, font=FG, fill="#4e5d3a")

    for name, lon, lat in parks_n[:20]:
        x, y = page.to_pt(lon, lat)
        if not ok(x, y, 22):
            continue
        svg.raw('<rect x="%.1f" y="%.1f" width="7" height="7" rx="1.2" fill="#ffffff" stroke="%s" stroke-width="0.8"/>'
                % (x - 3.5, y - 3.5, INK))
        svg.text(x, y + 2.3, "P", size=5.6, font=FG_SEMI, fill=INK)

    for nm, (L, pts) in sorted(rivers.items(), key=lambda kv: -kv[1][0])[:14]:
        if L < 90:
            continue
        x, y, a = _point_at(pts, L * 0.45)
        if not _in_frame(page, x, y, -12):
            continue
        svg.text(x, y - 2.4, nm, size=6.6, font=FLECHA_BI, fill="#4f7d99", angle=a)

    p = svg.save(os.path.join(d["svg"], "labels.svg"))
    log("labels: %d places, %d peaks, %d camps, %d rivers" %
        (len(places), len(peaks), len(camps), len(rivers)))
    return p


def _ele_txt(ele):
    try:
        return "%d" % round(float(str(ele).replace("m", "").strip()))
    except Exception:
        return ""


# ------------------------------------------------------------------ locator + frame
NE_LAND = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
           "master/geojson/ne_110m_land.geojson")


def _albers_usa(lon, lat):
    """Conus Albers (EPSG:5070-ish, spherical approximation, fine for a locator)."""
    lam = math.radians(lon + 96)
    phi = math.radians(lat)
    phi1, phi2, phi0 = math.radians(29.5), math.radians(45.5), math.radians(23)
    n = (math.sin(phi1) + math.sin(phi2)) / 2
    C = math.cos(phi1) ** 2 + 2 * n * math.sin(phi1)
    rho = math.sqrt(C - 2 * n * math.sin(phi)) / n
    rho0 = math.sqrt(C - 2 * n * math.sin(phi0)) / n
    th = n * lam
    return rho * math.sin(th), rho0 - rho * math.cos(th)


def locator_svg(job, page, log):
    d = job["dirs"]
    w, s, e, n = page.bbox
    conus = -125 < (w + e) / 2 < -66 and 24 < (s + n) / 2 < 50
    svg = SVG(page)
    # locator box in the meta strip, right side
    bw, bh = 86, 54
    bx = page.w - util.MARGIN - bw
    by = page.h - util.MARGIN - bh + 6

    if conus:
        from .vectors import _states_geojson
        states = _states_geojson(log)
        pts_all = []
        polys = []
        for ft in states["features"]:
            if ft["properties"]["STATEFP"] in ("02", "15", "72", "78", "66", "60", "69"):
                continue
            for rings in _polys(ft["geometry"]):
                ring = [( _albers_usa(c[0], c[1])) for c in rings[0]]
                polys.append(ring)
                pts_all.extend(ring)
    else:
        cache = os.path.join(util.CACHE, "ne")
        os.makedirs(cache, exist_ok=True)
        land = fetch(NE_LAND, os.path.join(cache, "ne_110m_land.geojson"), log=log)
        with open(land, encoding="utf-8") as f:
            fc = json.load(f)
        polys = []
        pts_all = []
        for ft in fc["features"]:
            for rings in _polys(ft["geometry"]):
                ring = [(c[0] * math.pi / 180,
                         math.log(math.tan(math.pi / 4 + min(max(c[1], -80), 80) * math.pi / 360)))
                        for c in rings[0]]
                polys.append(ring)
                pts_all.extend(ring)

    xs = [p[0] for p in pts_all]
    ys = [p[1] for p in pts_all]
    sc = min((bw - 6) / (max(xs) - min(xs)), (bh - 6) / (max(ys) - min(ys)))
    ox = bx + bw / 2 - (min(xs) + max(xs)) / 2 * sc
    oy = by + bh / 2 + (min(ys) + max(ys)) / 2 * sc

    def tx(p):
        return ox + p[0] * sc, oy - p[1] * sc

    svg.raw('<rect x="%.1f" y="%.1f" width="%d" height="%d" fill="#ece7d8" stroke="#8a8468" stroke-width="0.5"/>'
            % (bx, by, bw, bh))
    for ring in polys:
        svg.poly([[tx(p) for p in ring]], "#dcd6c4", stroke="#a8a28c", width=0.3)
    proj = _albers_usa if conus else (lambda lo, la: (
        lo * math.pi / 180, math.log(math.tan(math.pi / 4 + min(max(la, -80), 80) * math.pi / 360))))
    corners = [(w, s), (e, s), (e, n), (w, n)]
    box = [tx(proj(lo, la)) for lo, la in corners]
    svg.poly([box], "none", stroke="#b03a2e", width=1.1)
    svg.raw('<path d="M%.1f %.1f L%.1f %.1f Z" fill="#b03a2e"/>' % (
        box[0][0], box[0][1], box[0][0], box[0][1]))
    p = svg.save(os.path.join(d["svg"], "locator.svg"), clip_to_frame=False)
    return p


def frame_svg(job, page, log):
    d = job["dirs"]
    svg = SVG(page)
    fx0, fy0, fx1, fy1 = page.frame
    # paper + neatline
    svg.raw('<rect x="0" y="0" width="%d" height="%d" fill="%s"/>' % (page.w, page.h, PAPER))
    svg.raw('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#ffffff"/>'
            % (fx0, fy0, fx1 - fx0, fy1 - fy0))
    p = svg.save(os.path.join(d["svg"], "frame.svg"), clip_to_frame=False)

    meta = SVG(page)
    meta.raw('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="none" stroke="%s" stroke-width="1.1"/>'
             % (fx0, fy0, fx1 - fx0, fy1 - fy0, INK))
    title = job["params"].get("title") or "RELIEF SHEET"
    y0 = fy1 + 20
    meta.text(fx0, y0, title, size=15, font=FG_SEMI, fill=INK, anchor="start", upper=True, tracking=0.8)
    w, s, e, n = page.bbox
    sub = "%.4f° %s  %.4f° %s   to   %.4f° %s  %.4f° %s      1:%s      UTM %d" % (
        abs(s), "N" if s >= 0 else "S", abs(w), "E" if w >= 0 else "W",
        abs(n), "N" if n >= 0 else "S", abs(e), "E" if e >= 0 else "W",
        "{:,}".format(int(round(page.scale, -2))), page.epsg % 100)
    meta.text(fx0, y0 + 13, sub, size=7, font=FG, fill="#6a645a", anchor="start")
    cred = ("Relief: USGS 3DEP / Copernicus DEM (ESA)   Landcover: ESA WorldCover (CC BY 4.0)   "
            "Roads: US Census TIGER, (c) OpenStreetMap contributors   Ownership: USGS PAD-US")
    meta.text(fx0, y0 + 24, cred, size=5.4, font=FG, fill="#8a8478", anchor="start")
    # scale bar: nice round km (1 pt on paper = scale * 0.0254/72 m on the ground)
    m_per_pt = page.scale * 0.0254 / 72
    km100 = m_per_pt * 100 / 1000.0
    nice = [0.5, 1, 2, 5, 10, 20, 25, 50, 100, 200]
    pick_km = min(nice, key=lambda v: abs(v - km100 * 1.2))
    bar_pt = pick_km * 1000 / m_per_pt
    bx1 = fx0
    by1 = y0 + 34
    meta.raw('<path d="M%.1f %.1f L%.1f %.1f" stroke="%s" stroke-width="1.6"/>' % (
        bx1, by1, bx1 + bar_pt, by1, INK))
    for t in (0, 0.5, 1):
        meta.raw('<path d="M%.1f %.1f L%.1f %.1f" stroke="%s" stroke-width="0.8"/>' % (
            bx1 + bar_pt * t, by1 - 3, bx1 + bar_pt * t, by1, INK))
    meta.text(bx1 + bar_pt / 2, by1 + 8, "%g km" % pick_km, size=6, font=FG, fill=INK)
    p2 = meta.save(os.path.join(d["svg"], "metadata.svg"), clip_to_frame=False)
    return p, p2
