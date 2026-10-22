"""N-panel UI. One panel, organised by workflow tabs: Create, Shape, Detail, Style, Export."""

import bpy

from ..core import modifier, project
from ..core.presets import DISTRIBUTION_MODES, STRAND_PRESETS, WIDTH_PROFILES
from ..materials import shader_builder


def _prop(layout, mod, name, text=None, **kw):
    s = modifier.input_struct(mod, name)
    if s is not None:
        layout.prop(s, "value", text=name if text is None else text, **kw)


def _section(layout, title, icon="NONE"):
    box = layout.box()
    box.label(text=title, icon=icon)
    return box.column(align=True)


class VIEW3D_PT_strandforge(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "StrandForge"
    bl_label = "StrandForge"

    def draw(self, context):
        layout = self.layout
        sf = project.settings(context)

        if sf.collection is None:
            self._draw_new_project(layout, sf)
            return

        self._draw_regions(layout, context, sf)
        ob = project.active_region(context)
        row = layout.row(align=True)
        row.prop(sf, "ui_tab", expand=True, icon_only=True)
        row.scale_y = 1.3
        layout.label(text=sf.bl_rna.properties["ui_tab"].enum_items[sf.ui_tab].name.upper())

        mod = modifier.find(ob)
        if sf.ui_tab != "EXPORT" and mod is None:
            layout.label(text="Select a region to edit it", icon="INFO")
            return
        getattr(self, "_tab_" + sf.ui_tab.lower())(layout, context, sf, ob, mod)

    # -- project -----------------------------------------------------------
    def _draw_new_project(self, layout, sf):
        col = _section(layout, "New Hair Project", "OUTLINER_OB_CURVES")
        col.prop(sf, "character")
        col.prop(sf, "head")
        col.separator()
        col.operator("strandforge.create_project", icon="ADD")

    def _draw_regions(self, layout, context, sf):
        box = layout.box()
        row = box.row()
        row.label(text=f"{sf.character}", icon="OUTLINER_OB_CURVES")
        row.prop(sf, "head", text="")
        active = context.active_object
        for ob in project.regions(context.scene):
            r = box.row(align=True)
            is_active = ob == active
            r.operator("strandforge.select_region", text=ob.name.split("_", 2)[-1],
                       icon="RADIOBUT_ON" if is_active else "RADIOBUT_OFF", depress=is_active).name = ob.name
            r.label(text=str(len(ob.data.curves)))
            r.operator("strandforge.isolate_region", text="", icon="SOLO_OFF").name = ob.name
            r.prop(ob, "hide_viewport", text="", emboss=False)
        box.operator_menu_enum("strandforge.add_region", "region_type", text="Add Region", icon="ADD")

    # -- tabs --------------------------------------------------------------
    def _tab_create(self, layout, context, sf, ob, mod):
        col = _section(layout, "Draw Strand", "GREASEPENCIL")
        row = col.row(align=True)
        row.scale_y = 1.4
        row.operator("strandforge.draw_strand", text="Surface", icon="SURFACE_DATA").mode = "SURFACE"
        row.operator("strandforge.draw_strand", text="Free", icon="CURVE_BEZCURVE").mode = "FREE"
        row.operator("strandforge.draw_strand", text="Extend", icon="FORWARD").mode = "EXTEND"
        col.separator()
        col.prop(sf, "draw_preset", text="Preset")
        col.prop(sf, "draw_offset")
        col.prop(sf, "draw_smooth")
        col.prop(sf, "draw_points")

        col = _section(layout, "Edit Strands", "OUTLINER_DATA_CURVES")
        row = col.row(align=True)
        row.operator("object.mode_set", text="Edit", icon="EDITMODE_HLT").mode = "EDIT"
        row.operator("object.mode_set", text="Sculpt", icon="SCULPTMODE_HLT").mode = "SCULPT_CURVES"
        row.operator("object.mode_set", text="Object", icon="OBJECT_DATAMODE").mode = "OBJECT"
        col.operator("strandforge.duplicate_variation", icon="DUPLICATE")
        col.operator("strandforge.attach_to_scalp", icon="SNAP_FACE")
        col.operator("strandforge.strand_width", icon="ARROW_LEFTRIGHT")
        col.operator("strandforge.toggle_preview", icon="HIDE_OFF")

        col = _section(layout, "Strand Presets", "PRESET")
        col.label(text="Assign to selected strands:")
        grid = col.grid_flow(columns=2, align=True)
        grid.operator("strandforge.assign_strand_preset", text="Region").preset = "REGION"
        for key, (label, _d, _s) in STRAND_PRESETS.items():
            grid.operator("strandforge.assign_strand_preset", text=label).preset = key
        col.separator()
        col.operator_menu_enum("strandforge.apply_region_preset", "preset", text="Set Region Shape From…")

        col = _section(layout, "Library", "ASSET_MANAGER")
        row = col.row(align=True)
        row.operator("strandforge.save_user_preset", text="Save", icon="FILE_TICK")
        row.operator("strandforge.load_user_preset", text="Load", icon="IMPORT")
        row.operator("strandforge.delete_user_preset", text="", icon="TRASH")
        row.operator("strandforge.open_library_folder", text="", icon="FILE_FOLDER")

    def _tab_shape(self, layout, context, sf, ob, mod):
        col = _section(layout, "Size", "ARROW_LEFTRIGHT")
        _prop(col, mod, "Width")
        _prop(col, mod, "Thickness Ratio", "Thickness")
        _prop(col, mod, "Width Variation", "Variation")

        col = _section(layout, "Width Along Strand", "IPO_EASE_IN_OUT")
        row = col.row(align=True)
        for key, (label, _v) in WIDTH_PROFILES.items():
            row.operator("strandforge.width_profile", text=label).profile = key
        col.separator()
        _prop(col, mod, "Root Width")
        _prop(col, mod, "Peak Position")
        _prop(col, mod, "Tip Width")
        _prop(col, mod, "Taper Power")
        _prop(col, mod, "Close Root")

        box = layout.box()
        box.label(text="Cross-Section Profile", icon="MESH_CIRCLE")
        split = box.split(factor=0.5, align=True)
        for end, c in (("Root", split.column(align=True)), ("Tip", split.column(align=True))):
            c.label(text=end)
            _prop(c, mod, f"{end} Sharpness", "Sharpness")
            _prop(c, mod, f"{end} Teardrop", "Teardrop")
            _prop(c, mod, f"{end} Asymmetry", "Asymmetry")
            _prop(c, mod, f"{end} Flatten", "Flatten")

        col = _section(layout, "Twist & Orientation", "FORCE_VORTEX")
        _prop(col, mod, "Align to Scalp")
        _prop(col, mod, "Profile Rotation", "Roll")
        _prop(col, mod, "Twist", "Twist (turns)")
        _prop(col, mod, "Roll Variation")

        col = _section(layout, "Resolution", "MESH_GRID")
        _prop(col, mod, "Length Segments")
        _prop(col, mod, "Ring Segments")

    def _tab_detail(self, layout, context, sf, ob, mod):
        col = _section(layout, "Detail Quality (viewport)", "PREFERENCES")
        col.row(align=True).prop(sf, "quality", expand=True)

        box = layout.box()
        row = box.row()
        row.label(text="Secondary Strands", icon="PARTICLES")
        _prop(row, mod, "Secondary Strands", "")
        col = box.column(align=True)
        col.active = bool(modifier.get(mod, "Secondary Strands", True))
        row = col.row(align=True)
        for key, (label, _d, _v) in DISTRIBUTION_MODES.items():
            row.operator("strandforge.distribution_mode", text=label).mode = key
        col.separator()
        _prop(col, mod, "Strand Count", "Density (per strand)")
        for label, a, b, ta, tb in (("Width", "Width Min", "Width Max", "Min", "Max"),
                                    ("Length", "Length Min", "Length Max", "Min", "Max"),
                                    ("Range", "Root Bias", "Tip Bias", "Root", "Tip")):
            r = col.split(factor=0.3, align=True)
            r.label(text=label)
            _prop(r, mod, a, ta)
            _prop(r, mod, b, tb)
        _prop(col, mod, "Coverage")
        _prop(col, mod, "Surface Offset")
        _prop(col, mod, "Secondary Thickness", "Thickness")
        _prop(col, mod, "Flow Variation")
        _prop(col, mod, "Flow Frequency")
        r = col.row(align=True)
        _prop(r, mod, "Seed")
        r.operator("strandforge.new_seed", text="", icon="FILE_REFRESH")
        col.separator()
        _prop(col, mod, "Secondary Length Segments", "Length Segments")
        _prop(col, mod, "Secondary Ring Segments", "Ring Segments")

        self._draw_stats(layout, sf)

    def _draw_stats(self, layout, sf):
        col = _section(layout, "Hair Performance", "INFO")
        if sf.stat_triangles >= 0:
            col.label(text=f"Triangles: {sf.stat_triangles:,}".replace(",", " "))
            col.label(text=f"Guide strands: {sf.stat_strands}")
            ratio = sf.stat_triangles / max(sf.triangle_budget, 1)
            col.progress(factor=min(ratio, 1.0), text=f"{ratio:.0%} of budget")
            if ratio > 1.0:
                col.label(text="Over triangle budget", icon="ERROR")
        col.prop(sf, "triangle_budget")
        col.operator("strandforge.update_stats", icon="FILE_REFRESH")

    def _tab_style(self, layout, context, sf, ob, mod):
        col = _section(layout, "Material", "MATERIAL")
        _prop(col, mod, "Material", "")
        mat = modifier.get(mod, "Material")
        ramp = shader_builder.gradient_node(mat)
        if ramp is not None:
            layout.label(text="Root → Tip Color")
            layout.template_color_ramp(ramp, "color_ramp", expand=True)
        bsdf = shader_builder.bsdf_node(mat)
        if bsdf is not None:
            col = _section(layout, "Surface", "SHADING_RENDERED")
            for name in ("Roughness", "Coat Weight", "Specular IOR Level"):
                if name in bsdf.inputs:
                    col.prop(bsdf.inputs[name], "default_value", text=name)
        layout.label(text="Material presets arrive in v0.3", icon="INFO")

    def _tab_export(self, layout, context, sf, ob, mod):
        col = _section(layout, "Bake", "MESH_DATA")
        col.operator("strandforge.bake_mesh", text="Bake Active Region", icon="MESH_DATA").all_regions = False
        op = col.operator("strandforge.bake_mesh", text="Bake All Visible Regions", icon="OUTLINER_OB_MESH")
        op.all_regions = True
        col.label(text="Baked copies go to a separate collection;")
        col.label(text="the curves stay editable.")
        self._draw_stats(layout, sf)
        layout.label(text="LOD, rigging and Unreal export: v1.0", icon="INFO")


class VIEW3D_MT_strandforge_quick(bpy.types.Menu):
    bl_label = "StrandForge"
    bl_idname = "VIEW3D_MT_strandforge_quick"

    def draw(self, context):
        layout = self.layout
        layout.operator("strandforge.draw_strand", text="Draw Strand (Surface)", icon="SURFACE_DATA").mode = "SURFACE"
        layout.operator("strandforge.draw_strand", text="Draw Strand (Free)", icon="CURVE_BEZCURVE").mode = "FREE"
        layout.operator("strandforge.draw_strand", text="Extend Strand", icon="FORWARD").mode = "EXTEND"
        layout.separator()
        layout.operator("strandforge.duplicate_variation", icon="DUPLICATE")
        layout.operator("strandforge.attach_to_scalp", icon="SNAP_FACE")
        layout.operator_menu_enum("strandforge.assign_strand_preset", "preset", text="Assign Preset")
        layout.separator()
        layout.operator("strandforge.toggle_preview", icon="HIDE_OFF")
        layout.operator_menu_enum("strandforge.set_quality", "quality", text="Detail Quality")


CLASSES = (VIEW3D_PT_strandforge, VIEW3D_MT_strandforge_quick)
