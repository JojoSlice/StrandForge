"""Render a Workbench preview of the test scene.

    blender --background --factory-startup --python tests/render_preview.py -- out.png [preset_key]
"""

import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import test_nodes  # noqa: E402
from strandforge.core import modifier as M  # noqa: E402
from strandforge.core.presets import STRAND_PRESETS  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out = argv[0] if argv else os.path.join(os.getcwd(), "preview.png")

ob, mod, _ids, cd = test_nodes.make_scene()
if len(argv) > 1:
    for name, value in STRAND_PRESETS[argv[1]][2].items():
        M.set(mod, name, value)
for kv in argv[2:]:
    k, v = kv.split("=")
    M.set(mod, k, type(M.get(mod, k))(eval(v)))

scene = bpy.context.scene
cam_data = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_data)
scene.collection.objects.link(cam)
target = bpy.data.objects.new("Target", None)
scene.collection.objects.link(target)
target.location = (0.0, 0.0, -0.04)
dist = float(os.environ.get("SF_CAM_DIST", "0.75"))
yaw = math.radians(float(os.environ.get("SF_CAM_YAW", "140")))
cam.location = (dist * math.sin(yaw), -dist * math.cos(yaw), 0.08)
track = cam.constraints.new("TRACK_TO")
track.target = target
cam_data.lens = 50
scene.camera = cam
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "OBJECT"
scene.display.shading.show_cavity = True
ob.color = (0.95, 0.55, 0.7, 1)
scene.render.resolution_x = 900
scene.render.resolution_y = 700
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
print("WROTE", out)
