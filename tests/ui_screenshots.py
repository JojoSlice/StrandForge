"""Open Blender with UI, register StrandForge, screenshot every tab, then quit.

    blender --factory-startup --python tests/ui_screenshots.py -- <out_dir>
"""

import math
import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import strandforge  # noqa: E402
from strandforge.core import strands  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else os.path.join(ROOT, "screens")
os.makedirs(OUT, exist_ok=True)
TABS = ["CREATE", "SHAPE", "DETAIL", "STYLE", "EXPORT"]


def setup():
    bpy.context.preferences.view.show_splash = False
    strandforge.register()
    # Test only: show the panel in the default sidebar tab (the active tab is read-only from Python).
    from strandforge.ui import panels
    bpy.utils.unregister_class(panels.VIEW3D_PT_strandforge)
    panels.VIEW3D_PT_strandforge.bl_category = "Item"
    panels.VIEW3D_PT_strandforge.bl_order = -1
    bpy.utils.register_class(panels.VIEW3D_PT_strandforge)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.1, segments=48, ring_count=24)
    head = bpy.context.active_object
    head.name = "Nova_Head"
    bpy.ops.object.shade_smooth()
    sf = bpy.context.scene.strandforge
    sf.head = head
    bpy.ops.strandforge.create_project()
    bpy.ops.strandforge.add_region(region_type="BACK_HAIR")
    bpy.ops.strandforge.add_region(region_type="BANGS")
    bpy.ops.strandforge.select_region(name="SF_Nova_BackHair")
    ob = bpy.context.active_object
    from mathutils import Vector
    n = 14
    for c in range(n):
        az = math.radians(-85 + 170 * c / (n - 1)) + math.pi * 1.5
        pts = []
        for p in range(10):
            t = p / 9
            polar = math.radians(18 + 100 * min(t * 1.6, 1.0))
            r = 0.104 + 0.012 * t
            pts.append(Vector((r * math.sin(polar) * math.cos(az), -r * math.sin(polar) * math.sin(az),
                               r * math.cos(polar) - max(0.0, t - 0.62) * 0.35)))
        strands.add_strand(ob.data, pts)
    ob.data.update_tag()

    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            space = area.spaces.active
            space.show_region_ui = True
            space.shading.type = "SOLID"
            space.shading.color_type = "MATERIAL"
            r3d = space.region_3d
            r3d.view_distance = 0.6
            r3d.view_location = (0, 0, -0.05)
            from mathutils import Euler
            r3d.view_rotation = Euler((math.radians(80), 0, math.radians(150))).to_quaternion()


state = {"i": 0}


def _close_splash():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                with bpy.context.temp_override(window=window, area=area):
                    try:
                        bpy.ops.wm.splash_close()
                    except Exception:  # noqa: BLE001
                        pass


def step():
    sf = bpy.context.scene.strandforge
    i = state["i"]
    if i == 0:
        _close_splash()
    if i > 0:
        path = os.path.join(OUT, f"tab_{TABS[i - 1].lower()}.png")
        bpy.ops.screen.screenshot(filepath=path)
        print("SHOT", path)
    if i >= len(TABS):
        bpy.ops.wm.quit_blender()
        return None
    sf.ui_tab = TABS[i]
    for area in bpy.context.screen.areas:
        area.tag_redraw()
    state["i"] += 1
    return 1.5


setup()
bpy.app.timers.register(step, first_interval=3.0)
