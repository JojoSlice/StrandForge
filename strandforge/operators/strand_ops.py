"""Operators that act on individual strands or on a region's shape settings."""

import math
import random

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from mathutils import Matrix, Vector

from ..core import modifier, project, strands
from ..core.presets import DISTRIBUTION_MODES, STRAND_PRESETS, WIDTH_PROFILES


def _region_or_report(op, context):
    ob = project.active_region(context)
    if ob is None:
        op.report({"ERROR"}, "Select a StrandForge region first")
    return ob


def _refresh(ob):
    ob.data.update_tag()
    ob.update_tag()


def _head_eval(context, ob):
    head = ob.data.surface or project.settings(context).head
    if head is None or head.type != "MESH":
        return None
    return head.evaluated_get(context.evaluated_depsgraph_get())


class SF_OT_apply_region_preset(bpy.types.Operator):
    bl_idname = "strandforge.apply_region_preset"
    bl_label = "Apply Preset to Region"
    bl_description = "Copy a strand preset into the region's shape settings"
    bl_options = {"REGISTER", "UNDO"}

    preset: EnumProperty(items=[(k, v[0], v[1]) for k, v in STRAND_PRESETS.items()])

    def execute(self, context):
        ob = _region_or_report(self, context)
        if ob is None:
            return {"CANCELLED"}
        project.apply_preset_to_region(modifier.find(ob), self.preset)
        return {"FINISHED"}


class SF_OT_assign_strand_preset(bpy.types.Operator):
    bl_idname = "strandforge.assign_strand_preset"
    bl_label = "Assign Preset to Selected Strands"
    bl_description = "Give the selected strands their own preset (Region Settings = follow the region)"
    bl_options = {"REGISTER", "UNDO"}

    preset: EnumProperty(items=project.STRAND_PRESET_ITEMS)

    def execute(self, context):
        ob = _region_or_report(self, context)
        if ob is None:
            return {"CANCELLED"}
        curves = ob.data
        sel = strands.selected_curves(curves)
        if not sel:
            self.report({"WARNING"}, "No strands selected")
            return {"CANCELLED"}
        attr = strands.ensure_curve_attr(curves, "sf_preset", "INT")
        value = project.preset_attr_value(self.preset)
        for i in sel:
            attr.data[i].value = value
        _refresh(ob)
        self.report({"INFO"}, f"{len(sel)} strand(s) set to {self.preset.replace('_', ' ').title()}")
        return {"FINISHED"}


class SF_OT_strand_width(bpy.types.Operator):
    bl_idname = "strandforge.strand_width"
    bl_label = "Scale Selected Strand Width"
    bl_description = "Per-strand width multiplier for the selected strands"
    bl_options = {"REGISTER", "UNDO"}

    scale: FloatProperty(name="Width Scale", default=1.0, min=0.05, soft_max=4.0)

    def execute(self, context):
        ob = _region_or_report(self, context)
        if ob is None:
            return {"CANCELLED"}
        attr = strands.ensure_curve_attr(ob.data, "sf_width_offset", "FLOAT")
        for i in strands.selected_curves(ob.data):
            attr.data[i].value = self.scale - 1.0
        _refresh(ob)
        return {"FINISHED"}


class SF_OT_width_profile(bpy.types.Operator):
    bl_idname = "strandforge.width_profile"
    bl_label = "Width Profile"
    bl_description = "Apply a width-along-length shape to the region"
    bl_options = {"REGISTER", "UNDO"}

    profile: EnumProperty(items=[(k, v[0], "") for k, v in WIDTH_PROFILES.items()])

    def execute(self, context):
        ob = _region_or_report(self, context)
        if ob is None:
            return {"CANCELLED"}
        mod = modifier.find(ob)
        for name, value in zip(("Root Width", "Peak Position", "Tip Width", "Taper Power"),
                               WIDTH_PROFILES[self.profile][1]):
            modifier.set(mod, name, value)
        return {"FINISHED"}


class SF_OT_distribution_mode(bpy.types.Operator):
    bl_idname = "strandforge.distribution_mode"
    bl_label = "Distribution Mode"
    bl_description = "Preset for how secondary strands follow the main strand"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(items=[(k, v[0], v[1]) for k, v in DISTRIBUTION_MODES.items()])

    def execute(self, context):
        ob = _region_or_report(self, context)
        if ob is None:
            return {"CANCELLED"}
        mod = modifier.find(ob)
        for name, value in zip(("Flow Variation", "Width Min", "Width Max", "Length Min"),
                               DISTRIBUTION_MODES[self.mode][2]):
            modifier.set(mod, name, value)
        return {"FINISHED"}


class SF_OT_new_seed(bpy.types.Operator):
    bl_idname = "strandforge.new_seed"
    bl_label = "New Seed"
    bl_description = "Pick a new random seed for the detail generator"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ob = _region_or_report(self, context)
        if ob is None:
            return {"CANCELLED"}
        modifier.set(modifier.find(ob), "Seed", random.randint(0, 99999))
        return {"FINISHED"}


class SF_OT_attach_to_scalp(bpy.types.Operator):
    bl_idname = "strandforge.attach_to_scalp"
    bl_label = "Attach to Scalp"
    bl_description = "Snap the roots of the selected strands onto the head surface, dragging the strand along"
    bl_options = {"REGISTER", "UNDO"}

    offset: FloatProperty(name="Offset", default=0.002, min=0.0, soft_max=0.05, subtype="DISTANCE")
    falloff: FloatProperty(name="Falloff", default=0.5, min=0.0, max=1.0, subtype="FACTOR",
                           description="How far along the strand the root correction is blended")

    def execute(self, context):
        ob = _region_or_report(self, context)
        if ob is None:
            return {"CANCELLED"}
        head = _head_eval(context, ob)
        if head is None:
            self.report({"ERROR"}, "Region has no head surface")
            return {"CANCELLED"}
        curves = ob.data
        mw = ob.matrix_world
        imw = mw.inverted()
        offs = strands.offsets(curves)
        sel = strands.selected_curves(curves)
        for c in sel:
            start, stop = offs[c], offs[c + 1]
            root_w = mw @ curves.points[start].position
            loc, nor = strands.closest_on_surface(head, root_w)
            if loc is None:
                continue
            delta = imw.to_3x3() @ ((loc + nor * self.offset) - root_w)
            n = stop - start
            for k in range(n):
                t = k / max(n - 1, 1)
                w = 1.0 if self.falloff <= 0 else max(0.0, 1.0 - t / max(self.falloff, 1e-4)) ** 2
                curves.points[start + k].position = curves.points[start + k].position + delta * w
        _refresh(ob)
        self.report({"INFO"}, f"Attached {len(sel)} strand(s)")
        return {"FINISHED"}


class SF_OT_duplicate_variation(bpy.types.Operator):
    bl_idname = "strandforge.duplicate_variation"
    bl_label = "Duplicate & Variation"
    bl_description = "Duplicate the selected strands with controlled random variation"
    bl_options = {"REGISTER", "UNDO"}

    copies: IntProperty(name="Copies", default=3, min=1, max=100)
    length_var: FloatProperty(name="Length Variation", default=0.1, min=0.0, max=1.0, subtype="FACTOR")
    width_var: FloatProperty(name="Width Variation", default=0.15, min=0.0, max=1.0, subtype="FACTOR")
    bend_var: FloatProperty(name="Bend Variation", default=0.08, min=0.0, max=1.0, subtype="FACTOR")
    rotation_var: FloatProperty(name="Rotation Variation", default=math.radians(10), min=0.0, max=math.pi,
                                subtype="ANGLE")
    offset: FloatProperty(name="Position Offset", default=0.012, min=0.0, soft_max=0.1, subtype="DISTANCE")
    seed: IntProperty(name="Seed", default=0, min=0)
    preserve_root_direction: BoolProperty(
        name="Preserve Root Direction", default=True,
        description="Rotate progressively towards the tip so roots keep their direction",
    )
    keep_preset: BoolProperty(
        name="Linked to Preset", default=True,
        description="Copies keep the original's strand preset; off = copies follow region settings",
    )

    @classmethod
    def poll(cls, context):
        return project.active_region(context) is not None

    def execute(self, context):
        ob = project.active_region(context)
        curves = ob.data
        sel = strands.selected_curves(curves)
        if not sel:
            self.report({"WARNING"}, "No strands selected")
            return {"CANCELLED"}
        if len(sel) == len(curves.curves) and curves.attributes.get(".selection") is None and len(sel) > 1:
            self.report({"WARNING"}, "Select strands in Edit Mode first")
            return {"CANCELLED"}

        head = _head_eval(context, ob)
        mw = ob.matrix_world
        imw = mw.inverted()
        rng = random.Random(self.seed)
        new_indices = []
        for c in sel:
            pts = strands.curve_points(curves, c)
            if len(pts) < 2:
                continue
            root = pts[0]
            _loc, nor_w = strands.closest_on_surface(head, mw @ root)
            normal = (imw.to_3x3() @ nor_w).normalized() if nor_w else strands.fallback_normal(pts)
            direction = (pts[-1] - root)
            side = normal.cross(direction)
            side = side.normalized() if side.length > 1e-9 else Vector((1, 0, 0))
            tangent2 = normal.cross(side).normalized()
            length = strands.polyline_length(pts)
            n = len(pts)

            for _copy in range(self.copies):
                ls = 1.0 + rng.uniform(-1, 1) * self.length_var
                angle = rng.uniform(-1, 1) * self.rotation_var
                bend = rng.uniform(-1, 1) * self.bend_var * length
                shift = (side * rng.uniform(-1, 1) + tangent2 * rng.uniform(-1, 1) * 0.5) * self.offset
                new_pts = []
                for k, p in enumerate(pts):
                    t = k / (n - 1)
                    q = root + (p - root) * ls
                    q = q + side * (math.sin(math.pi * t) * bend)
                    a = angle * t if self.preserve_root_direction else angle
                    q = root + Matrix.Rotation(a, 3, normal) @ (q - root)
                    new_pts.append(q + shift)
                idx = strands.duplicate_strand(curves, c, new_pts)
                new_indices.append(idx)
                width = strands.ensure_curve_attr(curves, "sf_width_offset", "FLOAT")
                base = width.data[c].value
                width.data[idx].value = (1.0 + base) * (1.0 + rng.uniform(-1, 1) * self.width_var) - 1.0
                if not self.keep_preset:
                    strands.ensure_curve_attr(curves, "sf_preset", "INT").data[idx].value = 0

        strands.set_selection(curves, new_indices)
        _refresh(ob)
        self.report({"INFO"}, f"Created {len(new_indices)} strand(s)")
        return {"FINISHED"}


CLASSES = (
    SF_OT_apply_region_preset,
    SF_OT_assign_strand_preset,
    SF_OT_strand_width,
    SF_OT_width_profile,
    SF_OT_distribution_mode,
    SF_OT_new_seed,
    SF_OT_attach_to_scalp,
    SF_OT_duplicate_variation,
)
