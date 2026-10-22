"""Drive the Draw Strand modal tool with simulated mouse events (needs a window).

    blender --factory-startup --enable-event-simulate --python tests/ui_draw_test.py -- <out_dir>
"""

import math
import os
import sys

import bpy
from bpy_extras import view3d_utils
from mathutils import Euler, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import strandforge  # noqa: E402
from strandforge.core import strands  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else ROOT
RESULTS = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    RESULTS.append(cond)


def view3d():
    win = bpy.context.window_manager.windows[0]
    for area in win.screen.areas:
        if area.type == "VIEW_3D":
            region = next(r for r in area.regions if r.type == "WINDOW")
            return win, area, region, area.spaces.active.region_3d
    raise RuntimeError("no 3D view")


def to_window(p3):
    _win, _area, region, rv3d = view3d()
    p2 = view3d_utils.location_3d_to_region_2d(region, rv3d, p3)
    return int(p2.x + region.x), int(p2.y + region.y)


def setup():
    bpy.context.preferences.view.show_splash = False
    strandforge.register()
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.1, segments=48, ring_count=24)
    head = bpy.context.active_object
    bpy.context.scene.strandforge.head = head
    bpy.ops.strandforge.create_project()
    bpy.ops.strandforge.add_region(region_type="BANGS")
    _win, area, _region, rv3d = view3d()
    area.spaces.active.show_region_ui = False
    rv3d.view_perspective = "PERSP"
    rv3d.view_distance = 0.5
    rv3d.view_location = (0, 0, 0)
    rv3d.view_rotation = Euler((math.radians(75), 0, 0)).to_quaternion()  # looking at -Y face


def stroke_points(mode):
    # A stroke starting on the forehead and dragging downward across the face.
    pts = []
    for k in range(25):
        t = k / 24
        a = math.radians(55 - 50 * t)  # elevation angle on sphere
        if mode == "SURFACE":
            pts.append(Vector((0.02 * t, -0.1 * math.cos(a), 0.1 * math.sin(a))))
        else:
            pts.append(Vector((0.03, -0.1 * math.cos(math.radians(55)) - 0.002, 0.1 * math.sin(math.radians(55)) - 0.2 * t)))
    return pts


def schedule():
    events = []
    ob = bpy.context.active_object

    def start(mode):
        def f():
            win, area, region, _rv3d = view3d()
            with bpy.context.temp_override(window=win, area=area, region=region):
                bpy.ops.strandforge.draw_strand("INVOKE_DEFAULT", mode=mode)
        return f

    def drag(mode):
        def f():
            win = view3d()[0]
            coords = [to_window(p) for p in stroke_points(mode)]
            win.event_simulate("MOUSEMOVE", "NOTHING", x=coords[0][0], y=coords[0][1])
            win.event_simulate("LEFTMOUSE", "PRESS", x=coords[0][0], y=coords[0][1])
            for c in coords[1:]:
                win.event_simulate("MOUSEMOVE", "NOTHING", x=c[0], y=c[1])
            win.event_simulate("LEFTMOUSE", "RELEASE", x=coords[-1][0], y=coords[-1][1])
            win.event_simulate("ESC", "PRESS", x=coords[-1][0], y=coords[-1][1])
            win.event_simulate("ESC", "RELEASE", x=coords[-1][0], y=coords[-1][1])
        return f

    def verify_surface():
        check(len(ob.data.curves) == 1, f"surface stroke created a strand ({len(ob.data.curves)})")
        if len(ob.data.curves):
            pts = strands.curve_points(ob.data, 0)
            check(4 <= len(pts) <= 16, f"control points reduced ({len(pts)})")
            radii = [p.length for p in pts]
            check(all(0.098 < r < 0.11 for r in radii), f"points hug the surface ({min(radii):.3f}..{max(radii):.3f})")

    def verify_free():
        check(len(ob.data.curves) == 2, f"free stroke created a strand ({len(ob.data.curves)})")
        pts = strands.curve_points(ob.data, 1)
        check(abs(pts[0].length - 0.104) < 0.01, f"free root on head ({pts[0].length:.3f})")
        check(pts[-1].z < -0.05, f"free tip leaves the surface (z={pts[-1].z:.3f})")

    def verify_extend():
        n0 = len(strands.curve_points(ob.data, 1))
        check(len(ob.data.curves) == 2, "extend does not add a strand")
        check(state["free_len"] < n0, f"extend lengthened the strand ({state['free_len']} -> {n0})")

    state = {}

    def remember():
        state["free_len"] = len(strands.curve_points(ob.data, 1))

    def extend_drag():
        win = view3d()[0]
        tip = ob.matrix_world @ strands.curve_points(ob.data, 1)[-1]
        start = to_window(tip)
        win.event_simulate("MOUSEMOVE", "NOTHING", x=start[0], y=start[1])
        win.event_simulate("LEFTMOUSE", "PRESS", x=start[0], y=start[1])
        for k in range(1, 15):
            win.event_simulate("MOUSEMOVE", "NOTHING", x=start[0] + 4 * k, y=start[1] - 8 * k)
        win.event_simulate("LEFTMOUSE", "RELEASE", x=start[0] + 56, y=start[1] - 112)
        win.event_simulate("ESC", "PRESS", x=start[0], y=start[1])
        win.event_simulate("ESC", "RELEASE", x=start[0], y=start[1])

    def shot():
        bpy.ops.screen.screenshot(filepath=os.path.join(OUT, "draw_test.png"))

    def finish():
        print("RESULT", "OK" if all(RESULTS) else "FAILED")
        bpy.ops.wm.quit_blender()

    events += [start("SURFACE"), drag("SURFACE"), verify_surface,
               start("FREE"), drag("FREE"), verify_free,
               remember, start("EXTEND"), extend_drag, verify_extend, shot, finish]
    it = iter(events)

    def tick():
        try:
            fn = next(it)
        except StopIteration:
            return None
        fn()
        return 0.5

    bpy.app.timers.register(tick, first_interval=2.0)


setup()
schedule()
