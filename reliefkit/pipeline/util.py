"""Shared plumbing: shell, paths, projection, page geometry, tiny SVG writer."""
import json
import math
import os
import shutil
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "jobs")
CACHE = os.path.join(ROOT, "data_cache")
os.makedirs(JOBS, exist_ok=True)
os.makedirs(CACHE, exist_ok=True)

UA = {"User-Agent": "ReliefKit/1.0 (cartography tool; contact: local user)"}


def which_gdal(tool):
    """gdal tools: PATH first, then common Homebrew/QGIS/OSGeo locations."""
    p = shutil.which(tool) or shutil.which(tool + ".exe")
    if p:
        return p
    for base in ("/opt/homebrew/bin", "/usr/local/bin",
                 "/Applications/QGIS.app/Contents/MacOS/bin",
                 r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\Library\bin",
                 r"C:\Program Files\QGIS 3.34\bin", r"C:\OSGeo4W\bin"):
        c = os.path.join(base, tool + (".exe" if os.name == "nt" else ""))
        if os.path.exists(c):
            return c
    raise RuntimeError("%s not found; install GDAL (brew install gdal)" % tool)


def blender_path():
    p = shutil.which("blender")
    if p:
        return p
    for c in ("/Applications/Blender.app/Contents/MacOS/Blender",
              r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
              r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
              r"C:\Program Files\Blender Foundation\Blender\blender.exe"):
        if os.path.exists(c):
            return c
    return None


def run(cmd, log=print, check=True):
    log("$ " + " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.stdout.strip():
        log(r.stdout.strip()[-2000:])
    if r.returncode != 0:
        log(r.stderr.strip()[-2000:])
        if check:
            raise RuntimeError("command failed: " + str(cmd[0]))
    return r


def fetch(url, dest, log=print, post=None):
    """Download url -> dest (skip if cached). Returns dest."""
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        log("cached  " + os.path.basename(dest))
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    log("GET " + url[:160])
    req = urllib.request.Request(url, data=post, headers=UA)
    tmp = dest + ".part"
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as f:
        shutil.copyfileobj(resp, f)
    os.replace(tmp, dest)
    return dest


def fetch_json(url, log=print, post=None):
    req = urllib.request.Request(url, data=post, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ------------------------------------------------------------------ projection
def utm_epsg(lon, lat):
    zone = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


class TM:
    """Transverse Mercator (UTM) forward projection, series form, ~mm accurate.
    Hand-rolled so the vector pipeline needs no pyproj."""
    A = 6378137.0
    F = 1 / 298.257223563
    K0 = 0.9996

    def __init__(self, epsg):
        zone = epsg % 100
        self.south = epsg // 100 == 327
        self.lon0 = math.radians(zone * 6 - 183)
        f = self.F
        n = f / (2 - f)
        self.n = n
        self.AA = self.A / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
        self.alpha = [
            n / 2 - 2 * n**2 / 3 + 5 * n**3 / 16,
            13 * n**2 / 48 - 3 * n**3 / 5,
            61 * n**3 / 240,
        ]

    def forward(self, lon, lat):
        lam = math.radians(lon) - self.lon0
        phi = math.radians(lat)
        f = self.F
        e2 = f * (2 - f)
        e = math.sqrt(e2)
        t = math.sinh(math.atanh(math.sin(phi)) - e * math.atanh(e * math.sin(phi)))
        xi = math.atan2(t, math.cos(lam))
        eta = math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
        x, y = eta, xi
        for j, a in enumerate(self.alpha, 1):
            x += a * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
            y += a * math.sin(2 * j * xi) * math.cosh(2 * j * eta)
        E = self.K0 * self.AA * x + 500000
        N = self.K0 * self.AA * y + (10000000 if self.south else 0)
        return E, N


# ------------------------------------------------------------------ page
PAGES = {  # name -> (width_pt, height_pt)
    "letter-portrait": (612, 792),
    "letter-landscape": (792, 612),
    "tabloid-portrait": (792, 1224),
    "tabloid-landscape": (1224, 792),
    "slide-16x9": (960, 540),
    "square": (720, 720),
}
MARGIN = 36        # pt, left/right/top
META_STRIP = 72    # pt, bottom strip for title/locator/credits


class Page:
    """Fits the user bbox to the map frame, exposes lonlat->page-pt transform."""

    def __init__(self, preset, bbox):
        self.w, self.h = PAGES[preset]
        self.frame = (MARGIN, MARGIN, self.w - MARGIN, self.h - MARGIN - META_STRIP)
        fx0, fy0, fx1, fy1 = self.frame
        self.fw, self.fh = fx1 - fx0, fy1 - fy0

        lon0, lat0, lon1, lat1 = bbox
        self.epsg = utm_epsg((lon0 + lon1) / 2, (lat0 + lat1) / 2)
        self.tm = TM(self.epsg)
        x0, y0 = self.tm.forward(lon0, lat0)
        x1, y1 = self.tm.forward(lon1, lat1)
        bw, bh = abs(x1 - x0), abs(y1 - y0)
        # expand the short side so the box fills the frame exactly
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if bw / bh < self.fw / self.fh:
            bw = bh * self.fw / self.fh
        else:
            bh = bw * self.fh / self.fw
        self.x0, self.x1 = cx - bw / 2, cx + bw / 2
        self.y0, self.y1 = cy - bh / 2, cy + bh / 2
        self.scale = bw / (self.fw / 72 * 0.0254)   # denominator of 1:N
        # bbox back in lonlat (approx, for raster fetch padding)
        pad_lon = (lon1 - lon0) * (bw / abs(x1 - x0) - 1) / 2 if bw > abs(x1 - x0) else 0
        pad_lat = (lat1 - lat0) * (bh / abs(y1 - y0) - 1) / 2 if bh > abs(y1 - y0) else 0
        self.bbox = (lon0 - pad_lon, lat0 - pad_lat, lon1 + pad_lon, lat1 + pad_lat)

    def to_pt(self, lon, lat):
        x, y = self.tm.forward(lon, lat)
        fx0, fy0, fx1, fy1 = self.frame
        px = fx0 + (x - self.x0) / (self.x1 - self.x0) * self.fw
        py = fy0 + (1 - (y - self.y0) / (self.y1 - self.y0)) * self.fh
        return px, py

    def frame_px(self, dpi=300):
        return int(round(self.fw / 72 * dpi)), int(round(self.fh / 72 * dpi))


# ------------------------------------------------------------------ svg
class SVG:
    """Minimal layered SVG writer. One file per Illustrator layer; AI opens
    these and keeps text editable."""

    def __init__(self, page):
        self.p = page
        self.parts = []

    def path(self, coords_pt, stroke=None, width=1, fill="none", dash=None,
             cap="round", join="round", opacity=None, closed=False):
        if len(coords_pt) < 2:
            return
        d = "M" + " L".join("%.2f %.2f" % (x, y) for x, y in coords_pt)
        if closed:
            d += " Z"
        s = '<path d="%s" fill="%s"' % (d, fill)
        if stroke:
            s += ' stroke="%s" stroke-width="%.2f" stroke-linecap="%s" stroke-linejoin="%s"' % (
                stroke, width, cap, join)
        if dash:
            s += ' stroke-dasharray="%s"' % dash
        if opacity is not None:
            s += ' opacity="%.2f"' % opacity
        self.parts.append(s + "/>")

    def poly(self, rings_pt, fill, opacity=None, stroke=None, width=0.5):
        d = ""
        for ring in rings_pt:
            if len(ring) < 3:
                continue
            d += "M" + " L".join("%.2f %.2f" % (x, y) for x, y in ring) + " Z "
        if not d:
            return
        s = '<path d="%s" fill="%s" fill-rule="evenodd"' % (d.strip(), fill)
        if opacity is not None:
            s += ' fill-opacity="%.2f"' % opacity
        if stroke:
            s += ' stroke="%s" stroke-width="%.2f"' % (stroke, width)
        self.parts.append(s + "/>")

    def text(self, x, y, s, size=8, font="TestFoundersGroteskText-Regular",
             fill="#3b3b3b", anchor="middle", angle=0, tracking=None, upper=False):
        if upper:
            s = s.upper()
        esc = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        t = '<text x="%.2f" y="%.2f" font-family="%s" font-size="%.2f" fill="%s" text-anchor="%s"' % (
            x, y, font, size, fill, anchor)
        if tracking:
            t += ' letter-spacing="%.2f"' % tracking
        if angle:
            t += ' transform="rotate(%.1f %.2f %.2f)"' % (angle, x, y)
        self.parts.append(t + ">" + esc + "</text>")

    def raw(self, s):
        self.parts.append(s)

    def save(self, path, clip_to_frame=True):
        p = self.p
        fx0, fy0, fx1, fy1 = p.frame
        clip = ""
        body = "\n".join(self.parts)
        if clip_to_frame:
            clip = ('<clipPath id="frame"><rect x="%.1f" y="%.1f" width="%.1f" height="%.1f"/></clipPath>'
                    % (fx0, fy0, fx1 - fx0, fy1 - fy0))
            body = '<g clip-path="url(#frame)">\n%s\n</g>' % body
        doc = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<svg xmlns="http://www.w3.org/2000/svg" width="%dpt" height="%dpt" '
               'viewBox="0 0 %d %d">\n<defs>%s</defs>\n%s\n</svg>\n'
               % (p.w, p.h, p.w, p.h, clip, body))
        with open(path, "w", encoding="utf-8") as f:
            f.write(doc)
        return path
