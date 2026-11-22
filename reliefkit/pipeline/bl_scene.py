# Blender-side script (runs inside blender -b -P bl_scene.py -- args).
# Displaced plane under a 315/45 sun, Cycles, orthographic top camera.
# args: heightmap.png out_base px_w px_h displacement texture(high|low)
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
HM, OUT, PXW, PXH, DISP, TEXTURE = argv[0], argv[1], int(argv[2]), int(argv[3]), float(argv[4]), argv[5]

scn = bpy.context.scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

aspect = PXH / PXW
bpy.ops.mesh.primitive_plane_add(size=2)
plane = bpy.context.active_object
plane.scale = (1, aspect, 1)
bpy.ops.object.transform_apply(scale=True)

# dense grid for the displacement
seg = 2000 if TEXTURE == "high" else 1200
m = plane.modifiers.new("subd", "SUBSURF")
m.subdivision_type = "SIMPLE"
m.levels = 1
m.render_levels = 1
# use a grid via subdivide instead: predictable vert count
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.subdivide(number_cuts=seg)
bpy.ops.object.mode_set(mode="OBJECT")
plane.modifiers.remove(m)

img = bpy.data.images.load(HM)
img.colorspace_settings.name = "Non-Color"
tex = bpy.data.textures.new("hm", "IMAGE")
tex.image = img
tex.extension = "EXTEND"

disp = plane.modifiers.new("disp", "DISPLACE")
disp.texture = tex
disp.texture_coords = "UV"
disp.strength = DISP
disp.mid_level = 0.0

mat = bpy.data.materials.new("white")
mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (1, 1, 1, 1)
bsdf.inputs["Roughness"].default_value = 1.0
try:
    bsdf.inputs["Specular IOR Level"].default_value = 0.0
except KeyError:
    try:
        bsdf.inputs["Specular"].default_value = 0.0
    except KeyError:
        pass
plane.data.materials.append(mat)

# classic NW sun
bpy.ops.object.light_add(type="SUN", location=(0, 0, 4))
sun = bpy.context.active_object
sun.data.energy = 4.5
sun.data.angle = 0.18 if TEXTURE == "high" else 0.35   # softer shadows on low
import math
sun.rotation_euler = (math.radians(45), 0, math.radians(135))  # light from the NW

# faint fill so shadows stay open
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.35
scn.world = w

bpy.ops.object.camera_add(location=(0, 0, 5), rotation=(0, 0, 0))
cam = bpy.context.active_object
cam.data.type = "ORTHO"
cam.data.ortho_scale = 2.0
cam.data.sensor_fit = "HORIZONTAL"
scn.camera = cam

scn.render.engine = "CYCLES"
scn.cycles.samples = 96 if TEXTURE == "high" else 48
scn.cycles.use_denoising = True
try:
    scn.cycles.device = "GPU"
except Exception:
    pass
scn.render.resolution_x = PXW
scn.render.resolution_y = PXH
scn.render.image_settings.file_format = "PNG"
scn.render.image_settings.color_mode = "BW"
scn.render.image_settings.color_depth = "16"
scn.view_settings.view_transform = "Standard"
scn.render.filepath = OUT + ".png"
bpy.ops.render.render(write_still=True)
print("RELIEFKIT RENDER OK", OUT + ".png")
