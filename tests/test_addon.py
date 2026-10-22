"""Headless integration test: register the add-on and drive its operators.

    blender --background --factory-startup --python tests/test_addon.py
"""

import os
import sys
import traceback

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import strandforge  # noqa: E402
from strandforge.core import modifier as M  # noqa: E402
from strandforge.core import project, strands  # noqa: E402
from test_nodes import FAILED, Snapshot, check  # noqa: E402


def mesh_of(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    geo = ob.evaluated_get(dg).evaluated_geometry()  # keep alive while reading the mesh
    return Snapshot(geo.mesh) if geo.mesh else None


def main():
    strandforge.register()
    scene = bpy.context.scene
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)

    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.1, segments=32, ring_count=16)
    head = bpy.context.active_object
    head.name = "Nova_Head"
    sf = scene.strandforge
    sf.character = "Nova"
    sf.head = head

    check(bpy.ops.strandforge.create_project() == {"FINISHED"}, "create project")
    check(sf.collection is not None and sf.collection.name == "SF_Nova_Hair", "project collection named")
    check(sf.material is not None, "project material created")

    check(bpy.ops.strandforge.add_region(region_type="PONYTAIL") == {"FINISHED"}, "add ponytail region")
    ob = bpy.context.active_object
    check(ob.name == "SF_Nova_Ponytail", f"region auto-named ({ob.name})")
    check(project.is_region(ob), "region flagged")
    mod = M.find(ob)
    check(M.get(mod, "Scalp") == head, "scalp wired into modifier")
    check(M.get(mod, "Strand Count") == 10, "region defaults applied")

    bpy.ops.strandforge.add_region(region_type="PONYTAIL")
    check(bpy.context.active_object.name == "SF_Nova_Ponytail_01", "second region gets suffix")
    bpy.ops.strandforge.select_region(name="SF_Nova_Ponytail")
    check(bpy.context.active_object == ob, "select region")

    # simulate two drawn strands (local space == world since head at origin)
    from mathutils import Vector
    for x in (-0.03, 0.03):
        pts = [Vector((x, -0.1 + 0.01 * t, 0.02 - 0.03 * t)) for t in range(8)]
        strands.add_strand(ob.data, pts)
    check(len(ob.data.curves) == 2, "strands added")
    m = mesh_of(ob)
    check(m is not None and len(m.vertices) > 500, "region generates mesh")
    print("materials", m.materials if m else None, sorted(m.attributes) if m else None)
    check(m is not None and m.materials and m.materials[0] == sf.material.name, "material assigned via nodes")

    strands.set_selection(ob.data, [1])
    check(strands.selected_curves(ob.data) == [1], "selection roundtrip")
    check(bpy.ops.strandforge.assign_strand_preset(preset="FLAT_RIBBON") == {"FINISHED"}, "assign preset")
    check(ob.data.attributes["sf_preset"].data[1].value == project.preset_attr_value("FLAT_RIBBON"),
          "preset attribute written")
    check(ob.data.attributes["sf_preset"].data[0].value == 0, "unselected strand untouched")

    before = len(ob.data.curves)
    check(bpy.ops.strandforge.duplicate_variation(copies=4, seed=3) == {"FINISHED"}, "duplicate & variation")
    check(len(ob.data.curves) == before + 4, "4 copies created")
    check(ob.data.attributes["sf_preset"].data[before].value == project.preset_attr_value("FLAT_RIBBON"),
          "copies linked to preset")
    check(strands.selected_curves(ob.data) == list(range(before, before + 4)), "copies selected")
    p_src = strands.curve_points(ob.data, 1)
    p_new = strands.curve_points(ob.data, before)
    check(any((a - b).length > 1e-5 for a, b in zip(p_src, p_new)), "copies vary")

    check(bpy.ops.strandforge.attach_to_scalp(offset=0.0) == {"FINISHED"}, "attach to scalp")
    root = strands.curve_points(ob.data, before)[0]
    check(abs(root.length - 0.1) < 0.01, f"root on head surface (|r|={root.length:.4f})")

    bpy.ops.strandforge.width_profile(profile="FULL")
    check(abs(M.get(mod, "Root Width") - 0.85) < 1e-6, "width profile applied")
    bpy.ops.strandforge.distribution_mode(mode="ORGANIC")
    check(abs(M.get(mod, "Flow Variation") - 0.9) < 1e-6, "distribution mode applied")
    bpy.ops.strandforge.apply_region_preset(preset="SHARP_ANIME")
    check(abs(M.get(mod, "Taper Power") - 0.8) < 1e-6, "region preset applied")

    sf.quality = "DRAFT"
    check(abs(M.get(mod, "Viewport Detail") - 0.15) < 1e-6, "quality propagates to regions")
    n_draft = len(mesh_of(ob).vertices)
    sf.quality = "FINAL"
    n_final = len(mesh_of(ob).vertices)
    check(n_draft < n_final, f"draft lighter than final ({n_draft} < {n_final})")

    check(bpy.ops.strandforge.update_stats() == {"FINISHED"}, "stats")
    check(sf.stat_triangles > 0 and sf.stat_strands == 6, f"stats values ({sf.stat_triangles}, {sf.stat_strands})")

    bpy.ops.strandforge.toggle_preview()
    check(not mod.show_viewport, "toggle preview hides mesh")
    bpy.ops.strandforge.toggle_preview()

    sf.quality = "DRAFT"
    check(bpy.ops.strandforge.bake_mesh(all_regions=False) == {"FINISHED"}, "bake")
    baked = bpy.data.objects.get("SM_Nova_Ponytail")
    check(baked is not None and baked.type == "MESH", "baked mesh object exists")
    check(baked is not None and len(baked.data.vertices) >= n_final, "bake uses full detail")
    check(baked is not None and "UVMap" in baked.data.uv_layers, "bake keeps UV map")
    check(sf.quality == "DRAFT", "quality restored after bake")
    check(project.is_region(bpy.data.objects["SF_Nova_Ponytail"]), "source curves kept")

    bpy.ops.strandforge.select_region(name="SF_Nova_Ponytail")
    from strandforge.operators import library
    check(bpy.ops.strandforge.save_user_preset("EXEC_DEFAULT", name="ZZ Test") == {"FINISHED"}, "save preset")
    M.set(mod, "Width", 0.5)
    check(bpy.ops.strandforge.load_user_preset(preset="ZZ Test") == {"FINISHED"}, "load preset")
    check(abs(M.get(mod, "Width") - 0.03) < 1e-6, "preset restores width")
    check(M.get(mod, "Scalp") == head, "preset does not touch scalp")
    os.remove(os.path.join(library.library_dir(), "ZZ Test.json"))

    strandforge.unregister()
    check(not hasattr(bpy.types.Scene, "strandforge"), "unregister clean")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        FAILED.append("exception")
    print("RESULT", "FAILED" if FAILED else "OK", FAILED)
    sys.exit(1 if FAILED else 0)
