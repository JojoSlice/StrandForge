"""Project, region and visibility operators."""

import bpy
from bpy.props import EnumProperty, StringProperty

from ..core import modifier, project


class SF_OT_create_project(bpy.types.Operator):
    bl_idname = "strandforge.create_project"
    bl_label = "Create Hair Project"
    bl_description = "Create the collection, base material and node setup for this character's hair"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        sf = project.settings(context)
        if sf.head is None and context.active_object and context.active_object.type == "MESH":
            sf.head = context.active_object
        if sf.head is None:
            self.report({"ERROR"}, "Pick the character's head mesh first")
            return {"CANCELLED"}
        project.ensure_project(context.scene)
        self.report({"INFO"}, f"Hair project for {sf.character} created")
        return {"FINISHED"}


class SF_OT_add_region(bpy.types.Operator):
    bl_idname = "strandforge.add_region"
    bl_label = "Add Region"
    bl_description = "Add a hair region (one curves object sharing the StrandForge setup)"
    bl_options = {"REGISTER", "UNDO"}
    bl_property = "region_type"

    region_type: EnumProperty(name="Region", items=project.REGION_TYPES, default="BACK_HAIR")
    label: StringProperty(name="Name", description="Custom name (optional)")

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        if project.settings(context).head is None:
            self.report({"WARNING"}, "No head mesh set: strands cannot snap to a surface")
        ob = project.create_region(context, self.region_type, self.label)
        self.report({"INFO"}, f"Created {ob.name}")
        return {"FINISHED"}


class SF_OT_select_region(bpy.types.Operator):
    bl_idname = "strandforge.select_region"
    bl_label = "Select Region"
    bl_description = "Make this region the active one"
    bl_options = {"REGISTER", "UNDO"}

    name: StringProperty()

    def execute(self, context):
        ob = bpy.data.objects.get(self.name)
        if ob is None:
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for other in context.view_layer.objects.selected:
            other.select_set(False)
        if ob.hide_get():
            ob.hide_set(False)
        context.view_layer.objects.active = ob
        ob.select_set(True)
        return {"FINISHED"}


class SF_OT_isolate_region(bpy.types.Operator):
    bl_idname = "strandforge.isolate_region"
    bl_label = "Isolate Region"
    bl_description = "Hide every other region (click again to show all)"
    bl_options = {"REGISTER", "UNDO"}

    name: StringProperty()

    def execute(self, context):
        regs = project.regions(context.scene)
        others = [r for r in regs if r.name != self.name]
        if others and all(r.hide_get() for r in others):
            for r in others:
                r.hide_set(False)
        else:
            for r in others:
                r.hide_set(True)
        return {"FINISHED"}


class SF_OT_toggle_preview(bpy.types.Operator):
    bl_idname = "strandforge.toggle_preview"
    bl_label = "Toggle Curve / Mesh Preview"
    bl_description = "Switch between seeing the generated mesh and only the guide curves"
    bl_options = {"REGISTER", "UNDO"}

    all_regions: bpy.props.BoolProperty(name="All Regions", default=False)

    def execute(self, context):
        targets = project.regions(context.scene) if self.all_regions else [project.active_region(context)]
        targets = [t for t in targets if t]
        if not targets:
            self.report({"WARNING"}, "No StrandForge region active")
            return {"CANCELLED"}
        state = not modifier.find(targets[0]).show_viewport
        for ob in targets:
            mod = modifier.find(ob)
            if mod:
                mod.show_viewport = state
        return {"FINISHED"}


class SF_OT_set_quality(bpy.types.Operator):
    bl_idname = "strandforge.set_quality"
    bl_label = "Set Detail Quality"
    bl_options = {"REGISTER", "UNDO"}

    quality: EnumProperty(items=(("DRAFT", "Draft", ""), ("PREVIEW", "Preview", ""), ("FINAL", "Final", "")))

    def execute(self, context):
        project.settings(context).quality = self.quality
        return {"FINISHED"}


CLASSES = (
    SF_OT_create_project,
    SF_OT_add_region,
    SF_OT_select_region,
    SF_OT_isolate_region,
    SF_OT_toggle_preview,
    SF_OT_set_quality,
)
