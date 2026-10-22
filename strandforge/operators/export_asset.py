"""Bake regions to standalone meshes and gather geometry statistics.

Baked meshes are separate objects (Source -> Generated -> Baked), so later
curve edits never overwrite a mesh that has already been rigged or weighted.
"""

import bpy

from ..core import modifier, project


def evaluated_mesh(context, ob):
    """The mesh produced by a region's modifier (temporary; copy before keeping)."""
    dg = context.evaluated_depsgraph_get()
    geo = ob.evaluated_get(dg).evaluated_geometry()
    return geo, geo.mesh


def triangle_count(mesh):
    return sum(p.loop_total - 2 for p in mesh.polygons)


class SF_OT_update_stats(bpy.types.Operator):
    bl_idname = "strandforge.update_stats"
    bl_label = "Update Statistics"
    bl_description = "Count triangles and strands for all regions (uses the current viewport quality)"

    def execute(self, context):
        sf = project.settings(context)
        tris = 0
        count = 0
        for ob in project.regions(context.scene):
            count += len(ob.data.curves)
            mod = modifier.find(ob)
            if mod is None or not mod.show_viewport:
                continue
            _geo, mesh = evaluated_mesh(context, ob)
            if mesh is not None:
                tris += triangle_count(mesh)
        sf.stat_triangles = tris
        sf.stat_strands = count
        return {"FINISHED"}


class SF_OT_bake_mesh(bpy.types.Operator):
    bl_idname = "strandforge.bake_mesh"
    bl_label = "Bake to Mesh"
    bl_description = "Create a separate mesh copy of the region(s) at full detail; the curves stay editable"
    bl_options = {"REGISTER", "UNDO"}

    all_regions: bpy.props.BoolProperty(name="All Visible Regions", default=False)
    join: bpy.props.BoolProperty(name="Join into One Object", default=True)

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        scene = context.scene
        sf = project.settings(context)
        targets = (
            [r for r in project.regions(scene) if r.visible_get()]
            if self.all_regions else [project.active_region(context)]
        )
        targets = [t for t in targets if t is not None]
        if not targets:
            self.report({"ERROR"}, "No region to bake")
            return {"CANCELLED"}

        prev_quality = sf.quality
        sf.quality = "FINAL"  # bakes always use full detail
        char = project.safe_name(sf.character)
        coll_name = f"SF_{char}_Baked"
        coll = bpy.data.collections.get(coll_name)
        if coll is None:
            coll = bpy.data.collections.new(coll_name)
            scene.collection.children.link(coll)

        baked = []
        try:
            for ob in targets:
                _geo, mesh = evaluated_mesh(context, ob)
                if mesh is None:
                    continue
                data = mesh.copy()
                data.name = ob.name.replace("SF_", "SM_", 1)
                new_ob = bpy.data.objects.new(data.name, data)
                new_ob.matrix_world = ob.matrix_world.copy()
                coll.objects.link(new_ob)
                baked.append(new_ob)
        finally:
            sf.quality = prev_quality

        if not baked:
            self.report({"ERROR"}, "Nothing was generated")
            return {"CANCELLED"}

        for o in context.view_layer.objects.selected:
            o.select_set(False)
        for o in baked:
            o.select_set(True)
        context.view_layer.objects.active = baked[0]
        if self.join and len(baked) > 1:
            bpy.ops.object.join()
            context.active_object.name = f"SM_{char}_Hair"
        self.report({"INFO"}, f"Baked {len(baked)} region(s) into '{coll_name}'")
        return {"FINISHED"}


CLASSES = (SF_OT_update_stats, SF_OT_bake_mesh)
