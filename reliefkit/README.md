# ReliefKit

Drag a box on the earth, get an Illustrator file with linked Photoshop relief,
in the Raven Maps / Eric Knight / Taveras register. Localhost tool, macOS-first
(the Adobe assembly step scripts Photoshop + Illustrator; everything before it
is plain GDAL/Blender/Python and also runs on Windows or Linux).

## What a job produces

```
jobs/<name>/
  data/         raw + warped rasters, geojson vectors (kept for re-runs)
  relief/       16-bit heightmap, GDAL multidirectional hillshade, Blender render
  psd/          relief_blender.psd, relief_gdal.psd  (landcover tint layer inside each)
  svg/          one SVG per vector layer, already in page coordinates
  ai/           <name>.ai  with linked PSDs + all vector layers
  job.json      every parameter, for refactors and re-runs
```

Illustrator layer stack (top to bottom): Metadata, Locator, Labels, Shields,
Roads (casing/fill sublayers per class), Contours (labels in a knockout group so
halos clip the lines, somethingaboutmaps-style), Land ownership, Water,
Relief GDAL (hidden), Relief Blender (linked PSD), Frame.

Each PSD: Landcover tint (bottom, Normal, repaintable) + Relief (Multiply) +
Levels adjustment on top. Change the tints in one place, AI updates.

## Data sources (all keyless)

| Layer | Source |
|---|---|
| DEM 10 m (US) | USGS 3DEP 1/3" via TNM Access API |
| DEM 30 m / 90 m (global) | Copernicus GLO-30 / GLO-90, AWS open data |
| Landcover | ESA WorldCover 10 m v200 (2021), AWS open data |
| Freeways / primary / secondary | US Census TIGER/Line PRISECROADS |
| Minor roads, tracks | OSM Overpass |
| Places, peaks, rivers, campgrounds, parking, water polys | OSM Overpass |
| Land ownership (BLM / USFS / NPS / state / county...) | USGS PAD-US Manager_Name FeatureServer |
| Locator basemaps | Census cartographic states 20 m; Natural Earth 110 m land |

## Install (macOS)

```
cd reliefkit
./install_mac.sh     # brew: gdal, blender, python3; pip: flask, requests
./run.sh             # http://localhost:8765
```

Blender, Photoshop and Illustrator are found automatically; any that are
missing just skip their stage (the GDAL relief and all vectors still arrive).

## Credits to print on the map

Relief: USGS 3DEP / Copernicus DEM (ESA). Landcover: ESA WorldCover (CC BY 4.0).
Roads: US Census Bureau TIGER/Line, (c) OpenStreetMap contributors (ODbL).
Ownership: USGS PAD-US. The metadata strip in the AI file carries these already.
