"""Draw Strand: drag in the viewport to create a guide curve on the active region.

Modes
    SURFACE  every point is projected onto the head (plus an offset)
    FREE     the root snaps to the head, the rest lies on a view-aligned plane through the root
    EXTEND   continue the nearest strand tip on a view-aligned plane
"""

import bpy
import gpu
from bpy.props import EnumProperty
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from ..core import project, strands

MIN_PIXEL_STEP = 6.0
NAV_EVENTS = {
    "MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "TRACKPADPAN", "TRACKPADZOOM",
    "NDOF_MOTION", "NUMPAD_1", "NUMPAD_3", "NUMPAD_7", "NUMPAD_5", "NUMPAD_PERIOD",
}


def _draw_callback(op, _context):
    if len(op.stroke) < 2:
        return
    try:
        shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    except ValueError:
        return
    batch = batch_for_shader(shader, "LINE_STRIP", {"pos": [tuple(p) for p in op.stroke]})
    region = bpy.context.region
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("NONE")
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", 3.0)
    shader.uniform_float("color", (1.0, 0.45, 0.65, 0.95))
    batch.draw(shader)
    gpu.state.blend_set("NONE")


class SF_OT_draw_strand(bpy.types.Operator):
    bl_idname = "strandforge.draw_strand"
    bl_label = "Draw Strand"
    bl_description = "Draw hair strands directly in the viewport (LMB drag, Enter/Esc to finish)"
    bl_options = {"REGISTER", "BLOCKING"}  # undo is pushed per stroke

    mode: EnumProperty(
        name="Mode",
        items=(
            ("SURFACE", "Surface", "Draw along the head surface", "SURFACE_DATA", 0),
            ("FREE", "Free", "Root on the head, rest on a view plane", "CURVE_BEZCURVE", 1),
            ("EXTEND", "Extend", "Continue the nearest strand from its tip", "FORWARD", 2),
        ),
        default="SURFACE",
    )

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "VIEW_3D" and project.active_region(context) is not None

    # -- projection --------------------------------------------------------
    def _ray(self, context, coord):
        region, rv3d = context.region, context.region_data
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        return origin, direction

    def _hit_head(self, context, coord):
        if self.head is None:
            return None, None
        origin, direction = self._ray(context, coord)
        mw = self.head.matrix_world
        imw = mw.inverted()
        o = imw @ origin
        d = (imw.to_3x3() @ direction).normalized()
        ok, loc, nor, _idx = self.head.ray_cast(o, d)
        if not ok:
            return None, None
        n = (mw.to_3x3().inverted().transposed() @ nor).normalized()
        return mw @ loc, n

    def _on_plane(self, context, coord, depth_point):
        return view3d_utils.region_2d_to_location_3d(context.region, context.region_data, coord, depth_point)

    def _project(self, context, coord, first):
        offset = self.sf.draw_offset
        if first and self.mode == "EXTEND":
            return self.extend_tip
        if first:
            loc, nor = self._hit_head(context, coord)
            if loc is not None:
                return loc + nor * offset
            if self.head is not None:
                return None  # roots must start on the head
            return self._on_plane(context, coord, context.scene.cursor.location)
        if self.mode == "SURFACE":
            loc, nor = self._hit_head(context, coord)
            if loc is not None:
                return loc + nor * offset
        return self._on_plane(context, coord, self.stroke[0] if self.mode != "SURFACE" else self.stroke[-1])

    # -- extend helpers ----------------------------------------------------
    def _nearest_tip(self, context, coord):
        curves = self.region_ob.data
        offs = strands.offsets(curves)
        mw = self.region_ob.matrix_world
        best, best_d = None, 40.0  # pixels
        for c in range(len(curves.curves)):
            tip = mw @ curves.points[offs[c + 1] - 1].position
            p2 = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, tip)
            if p2 is None:
                continue
            d = (p2 - Vector(coord)).length
            if d < best_d:
                best, best_d = c, d
        return best

    # -- stroke ------------------------------------------------------------
    def _begin(self, context, coord):
        self.extend_curve = None
        if self.mode == "EXTEND":
            c = self._nearest_tip(context, coord)
            if c is None:
                self.report({"WARNING"}, "Start the stroke on a strand tip")
                return
            self.extend_curve = c
            offs = strands.offsets(self.region_ob.data)
            self.extend_tip = self.region_ob.matrix_world @ self.region_ob.data.points[offs[c + 1] - 1].position
        p = self._project(context, coord, True)
        if p is None:
            self.report({"WARNING"}, "Start the stroke on the head")
            return
        self.drawing = True
        self.stroke = [p]
        self.last_coord = Vector(coord)

    def _add(self, context, coord):
        if (Vector(coord) - self.last_coord).length < MIN_PIXEL_STEP:
            return
        p = self._project(context, coord, False)
        if p is not None:
            self.stroke.append(p)
            self.last_coord = Vector(coord)

    def _commit(self, context):
        self.drawing = False
        pts = self.stroke
        self.stroke = []
        if len(pts) < 3 or strands.polyline_length(pts) < 1e-4:
            return
        pts = strands.smooth_polyline(pts, self.sf.draw_smooth)
        count = self.sf.draw_points or max(4, min(16, len(pts) // 4))
        pts = strands.resample_polyline(pts, count)

        ob = self.region_ob
        curves = ob.data
        imw = ob.matrix_world.inverted()
        local = [imw @ p for p in pts]

        if self.mode == "EXTEND" and self.extend_curve is not None:
            c = self.extend_curve
            old = strands.curve_points(curves, c)
            curves.resize_curves([len(old) + len(local) - 1], indices=[c])
            start = strands.offsets(curves)[c]
            for k, p in enumerate(local[1:], start=len(old)):
                curves.points[start + k].position = p
            strands.set_selection(curves, [c])
        else:
            index = strands.add_strand(curves, local)
            attr = strands.ensure_curve_attr(curves, "sf_preset", "INT")
            attr.data[index].value = project.preset_attr_value(self.sf.draw_preset)
            strands.set_selection(curves, [index])
        curves.update_tag()
        ob.update_tag()
        bpy.ops.ed.undo_push(message="Draw Strand")
        self.count += 1

    # -- modal -------------------------------------------------------------
    def invoke(self, context, event):
        self.sf = project.settings(context)
        self.region_ob = project.active_region(context)
        head = self.region_ob.data.surface or self.sf.head
        self.head = head.evaluated_get(context.evaluated_depsgraph_get()) if head and head.type == "MESH" else None
        if self.head is None and self.mode != "EXTEND":
            self.report({"WARNING"}, "No head mesh: strands are drawn on the 3D cursor plane")
        self.stroke = []
        self.drawing = False
        self.count = 0
        self.extend_tip = None
        self.extend_curve = None
        self._handle = bpy.types.SpaceView3D.draw_handler_add(_draw_callback, (self, context), "WINDOW", "POST_VIEW")
        context.workspace.status_text_set(
            f"StrandForge {self.mode.title()} Draw: LMB drag = strand · Enter/Esc/RMB = finish · MMB/scroll = navigate"
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _finish(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
        context.workspace.status_text_set(None)
        context.area.tag_redraw()

    def modal(self, context, event):
        context.area.tag_redraw()
        if event.type in NAV_EVENTS or (event.type == "MOUSEMOVE" and not self.drawing):
            return {"PASS_THROUGH"}
        coord = (event.mouse_region_x, event.mouse_region_y)
        if event.type == "LEFTMOUSE":
            if event.value == "PRESS":
                self._begin(context, coord)
            elif event.value == "RELEASE" and self.drawing:
                self._commit(context)
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE" and self.drawing:
            self._add(context, coord)
            return {"RUNNING_MODAL"}
        if event.type in {"RET", "NUMPAD_ENTER", "ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            if self.drawing:
                self.drawing = False
                self.stroke = []
                return {"RUNNING_MODAL"}
            self._finish(context)
            return {"FINISHED"} if self.count else {"CANCELLED"}
        return {"RUNNING_MODAL"}


CLASSES = (SF_OT_draw_strand,)
