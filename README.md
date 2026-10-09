# Rainmaker basemap

Glyphs and styles for the Rainmaker vector basemap on Esri World Basemap v2.

Glyph endpoint used by the styles:

```
https://evanapplegate.github.io/rainmaker-basemap/glyphs/{fontstack}/{range}.pbf
```

## Styles

- `styles/rainmaker_base.json` fills, water, vector relief, contours, roads, boundaries
- `styles/rainmaker_labels.json` all labels
- `styles/rainmaker_full.json` both in one style, for editing in Maputnik

## Fontstacks

Founders Grotesk Text Regular, Medium, Semibold, Bold. Flecha S Regular, Medium.

These are currently built from trial font files. Characters missing from the trials
(apostrophes, accents, ampersands, parentheses, slashes, and hyphens in Flecha) are filled
from Hanken Grotesk and Source Serif 4, both under the SIL Open Font License. See `licenses/`.
Rebuild from licensed files with `tools/build_glyphs.js` in the source project.
