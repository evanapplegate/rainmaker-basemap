// ReliefKit Illustrator assembly. "var JOB = {...};" is prepended.
// Builds <name>.ai: linked PSD reliefs + every vector SVG copied into its own
// named layer. Contour labels go into a knockout group over the contour lines
// (somethingaboutmaps halo technique: label stroke knocks the lines, nothing
// below the group is touched).
#target illustrator
app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;

function fileIf(p) { var f = new File(p); return f.exists ? f : null; }

function font(cands, fallback) {
    for (var i = 0; i < cands.length; i++) {
        try { return app.textFonts.getByName(cands[i]); } catch (e) {}
    }
    try { return app.textFonts.getByName(fallback); } catch (e) {}
    return app.textFonts[0];
}

var doc = app.documents.add(DocumentColorSpace.RGB, JOB.page[0], JOB.page[1]);
doc.rulerOrigin = [0, 0];
var H = JOB.page[1];

function addLayer(name) {
    var L = doc.layers.add();
    L.name = name;
    return L;
}

// SVG y grows down; AI y grows up. Imported SVG groups land where placed; we
// normalize by positioning the imported group at the page origin.
function importSVG(path, layer) {
    var f = fileIf(path);
    if (!f) return null;
    var g = layer.groupItems.createFromFile(f);
    g.position = [0, H];          // top-left of the SVG to top-left of the page
    return g;
}

function placeLinked(path, layer) {
    var f = fileIf(path);
    if (!f) return null;
    var p = layer.placedItems.add();
    p.file = f;
    // stretch to the frame rect
    var fx0 = JOB.frame[0], fy0 = JOB.frame[1], fx1 = JOB.frame[2], fy1 = JOB.frame[3];
    p.width = fx1 - fx0;
    p.height = fy1 - fy0;
    p.position = [fx0, H - fy0];
    return p;
}

var on = function (k) { return JOB.layers[k] !== false; };
var svg = JOB.dir + "/svg/";

// ---- bottom to top -------------------------------------------------------
var lyFrame = addLayer("Frame");
importSVG(svg + "frame.svg", lyFrame);

var lyRelB = addLayer("Relief - Blender (PSD)");
if (JOB.blender) placeLinked(JOB.dir + "/psd/relief_blender.psd", lyRelB);
else lyRelB.visible = false;

var lyRelG = addLayer("Relief - GDAL multidirectional (PSD)");
placeLinked(JOB.dir + "/psd/relief_gdal.psd", lyRelG);
lyRelG.visible = !JOB.blender;    // one relief on at a time

if (on("ownership")) {
    var lyOwn = addLayer("Land ownership (PAD-US)");
    importSVG(svg + "ownership.svg", lyOwn);
    lyOwn.opacity = 55;
}

if (on("water")) {
    var lyWF = addLayer("Water - fills");
    importSVG(svg + "water_fill.svg", lyWF);
    var lyWL = addLayer("Water - lines");
    importSVG(svg + "water_lines.svg", lyWL);
}

if (on("contours")) {
    var lyC = addLayer("Contours");
    var lines = importSVG(svg + "contours.svg", lyC);
    var labels = importSVG(svg + "contour_labels.svg", lyC);
    if (lines && labels) {
        // knockout group: labels' halo strokes punch the lines, not the relief
        var ko = lyC.groupItems.add();
        lines.moveToBeginning(ko);
        labels.moveToBeginning(ko);
        ko.artworkKnockout = KnockoutState.ENABLED;
        // halo: give every label a fat paper stroke that does the knocking
        var texts = labels.textFrames;
        for (var i = 0; i < texts.length; i++) {
            var tr = texts[i].textRange;
            tr.characterAttributes.strokeColor = makeRGB(255, 255, 255);
            tr.characterAttributes.strokeWeight = 1.2;
        }
    }
}

// ---- roads: casing + fill sublayer pairs per class -----------------------
function makeRGB(r, g, b) { var c = new RGBColor(); c.red = r; c.green = g; c.blue = b; return c; }

if (on("roads")) {
    var classes = ["track", "minor", "major", "state", "us", "interstate"];
    var lyRoads = addLayer("Roads");
    for (var ci = 0; ci < classes.length; ci++) {
        var cls = classes[ci];
        var cas = fileIf(svg + "roads_" + cls + "_casing.svg");
        var fil = fileIf(svg + "roads_" + cls + "_fill.svg");
        if (!cas && !fil) continue;
        var sub = lyRoads.layers.add();
        sub.name = cls;
        if (cas) importSVG(cas.fsName, sub);
        if (fil) importSVG(fil.fsName, sub);
    }
}

if (on("shields")) {
    var lyS = addLayer("Highway shields");
    importSVG(svg + "shields.svg", lyS);
}

if (on("labels")) {
    var lyL = addLayer("Labels");
    importSVG(svg + "labels.svg", lyL);
}

if (on("locator")) {
    var lyLoc = addLayer("Locator");
    importSVG(svg + "locator.svg", lyLoc);
}

var lyM = addLayer("Metadata");
importSVG(svg + "metadata.svg", lyM);

// ---- font fixup: map SVG family names to installed faces -----------------
var MAP = {
    "TestFoundersGroteskText-Regular": ["TestFoundersGroteskText-Regular", "FoundersGroteskText-Regular"],
    "TestFoundersGroteskText-Medium": ["TestFoundersGroteskText-Medium", "FoundersGroteskText-Medium"],
    "TestFoundersGroteskText-Semibold": ["TestFoundersGroteskText-Semibold", "FoundersGroteskText-Semibold"],
    "FlechaTestS-BoldItalic": ["FlechaTestS-BoldItalic", "FlechaS-BoldItalic"]
};
for (var ti = 0; ti < doc.textFrames.length; ti++) {
    var tf = doc.textFrames[ti];
    try {
        var fam = tf.textRange.characterAttributes.textFont.name;
        for (var key in MAP) {
            if (fam.indexOf(key) === 0 || fam === key) {
                tf.textRange.characterAttributes.textFont = font(MAP[key], "Optima-Regular");
            }
        }
    } catch (e) {}
}

var out = new File(JOB.dir + "/ai/" + JOB.name + ".ai");
var opts = new IllustratorSaveOptions();
opts.embedLinkedFiles = false;   // keep PSDs linked
opts.pdfCompatible = true;
doc.saveAs(out, opts);
"saved " + out.fsName;
