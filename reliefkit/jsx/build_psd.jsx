// ReliefKit Photoshop assembly. A "var JOB = {...};" line is prepended by the
// pipeline. For each relief flavor: Landcover tint (bottom, repaintable) +
// Relief (Multiply) + Levels on top. Saved as psd/relief_<flavor>.psd.
#target photoshop
app.displayDialogs = DialogModes.NO;

function buildOne(flavor) {
    var reliefFile = new File(JOB.dir + "/relief/relief_" + flavor + ".tif");
    if (!reliefFile.exists) return "skip " + flavor;
    var tintFile = new File(JOB.dir + "/relief/landcover_tint.tif");

    var doc = app.open(reliefFile);
    doc.changeMode(ChangeMode.RGB);
    doc.activeLayer.isBackgroundLayer = false;   // unlock so blend mode sticks
    doc.activeLayer.name = "Relief (" + flavor + ")";
    doc.activeLayer.blendMode = BlendMode.MULTIPLY;

    if (tintFile.exists) {
        var tint = app.open(tintFile);
        tint.selection.selectAll();
        tint.selection.copy();
        tint.close(SaveOptions.DONOTSAVECHANGES);
        app.activeDocument = doc;
        var lay = doc.paste();
        lay.name = "Landcover tint";
        lay.move(doc.layers[doc.layers.length - 1], ElementPlacement.PLACEAFTER);
        doc.activeLayer = doc.layers[0];
    }

    // Levels adjustment layer via Action Manager
    var d1 = new ActionDescriptor();
    var r1 = new ActionReference();
    r1.putClass(stringIDToTypeID("adjustmentLayer"));
    d1.putReference(charIDToTypeID("null"), r1);
    var d2 = new ActionDescriptor();
    d2.putClass(charIDToTypeID("Type"), charIDToTypeID("Lvls"));
    d1.putObject(charIDToTypeID("Usng"), stringIDToTypeID("adjustmentLayer"), d2);
    executeAction(charIDToTypeID("Mk  "), d1, DialogModes.NO);
    app.activeDocument.activeLayer.name = "Levels (tune relief here)";

    var out = new File(JOB.dir + "/psd/relief_" + flavor + ".psd");
    var opts = new PhotoshopSaveOptions();
    opts.maximizeCompatibility = true;
    doc.saveAs(out, opts, true);
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return "ok " + flavor;
}

var msgs = [];
if (JOB.blender) msgs.push(buildOne("blender"));
msgs.push(buildOne("gdal"));
msgs.join(", ");
