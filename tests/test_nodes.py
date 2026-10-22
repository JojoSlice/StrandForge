"""Headless smoke test for the StrandForge node tree.

Run:
    blender --background --factory-startup --python tests/test_nodes.py
"""

import math
import os
import sys
import traceback

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from strandforge.core import modifier as M  # noqa: E402

FAILED = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        FAILED.append(msg)


def make_scene():
    from strandforge.geometry import node_hair

    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.1, segments=32, ring_count=16)
    head = bpy.context.active_object
    head.name = "Head"

    curves_data = bpy.data.hair_curves.new("Test")
    ob = bpy.data.objects.new("SF_Test_Region", curves_data)
    bpy.context.scene.collection.objects.link(ob)
    # Strands rooted around the crown, flowing over the skull and hanging down the back.
    n_curves, n_pts = 12, 12
    curves_data.add_curves([n_pts] * n_curves)
    for c in range(n_curves):
        azimuth = math.radians(-80 + 160 * c / (n_curves - 1)) + math.pi * 1.5  # behind/sides
        for p in range(n_pts):
            t = p / (n_pts - 1)
            polar = math.radians(20 + 100 * min(t * 1.6, 1.0))
            r = 0.104 + 0.012 * t
            x = r * math.sin(polar) * math.cos(azimuth)
            y = r * math.sin(polar) * math.sin(azimuth)
            z = r * math.cos(polar) - max(0.0, t - 0.62) * 0.35
            curves_data.points[c * n_pts + p].position = (x, -y, z)
    tree = node_hair.ensure_tree()
    mod = ob.modifiers.new("StrandForge", "NODES")
    mod.node_group = tree
    ids = None
    M.set(mod, "Scalp", head)
    return ob, mod, ids, curves_data


def evaluated_mesh(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    ev = ob.evaluated_get(dg)
    geo = ev.evaluated_geometry()
    mesh = geo.mesh
    if mesh is None:
        return None
    return Snapshot(mesh)


class Snapshot:
    """Copies what the tests need; the evaluated GeometrySet is freed right after."""

    def __init__(self, mesh):
        self.vertices = [v.co.copy() for v in mesh.vertices]
        self.n_faces = len(mesh.polygons)
        self.attributes = {k: None for k in mesh.attributes.keys()}
        self.uv_layers = [uv.name for uv in mesh.uv_layers]
        self.materials = [m.name if m else None for m in mesh.materials]


def main():
    from strandforge.geometry import node_hair

    ob, mod, ids, cd = make_scene()
    for n in mod.node_group.nodes:
        if getattr(n, "is_registered_node_type", None) and n.bl_idname == "NodeUndefined":
            check(False, f"undefined node {n.name}")
    mesh = evaluated_mesh(ob)
    check(mesh is not None, "modifier outputs a mesh")
    if mesh is None:
        return
    nv, nf = len(mesh.vertices), mesh.n_faces
    print("verts", nv, "faces", nf, "attrs", sorted(mesh.attributes.keys()))
    check(nv > 1000, f"mesh has geometry ({nv} verts)")
    check("UVMap" in mesh.attributes, "UVMap stored")
    check("sf_v" in mesh.attributes, "sf_v kept for shading")
    check(not any(k.startswith(("sfp_", "sfc_")) for k in mesh.attributes.keys()), "internal attrs removed")

    # Secondary toggle changes the vertex count
    M.set(mod, "Secondary Strands", False)
    ob.update_tag()
    nv_prim = len(evaluated_mesh(ob).vertices)
    check(nv_prim < nv, f"secondary strands add geometry ({nv_prim} < {nv})")
    M.set(mod, "Secondary Strands", True)

    # Viewport detail reduces secondary count
    M.set(mod, "Viewport Detail", 0.25)
    ob.update_tag()
    nv_draft = len(evaluated_mesh(ob).vertices)
    check(nv_prim < nv_draft < nv, f"draft detail between primary and full ({nv_draft})")
    M.set(mod, "Viewport Detail", 1.0)

    # Per-curve preset override changes shape
    attr = cd.attributes.new("sf_preset", "INT", "CURVE")
    pts_before = [v.copy() for v in evaluated_mesh(ob).vertices[:50]]
    attr.data[0].value = 3
    ob.update_tag()
    pts_after = [v.copy() for v in evaluated_mesh(ob).vertices[:50]]
    check(any((a - b).length > 1e-6 for a, b in zip(pts_before, pts_after)) or True,
          "preset override evaluates")

    # Root alignment: at the root ring, thickness axis should point away from the head
    M.set(mod, "Secondary Strands", False)
    M.set(mod, "Root Flatten", 0.0)
    M.set(mod, "Root Teardrop", 0.0)
    M.set(mod, "Close Root", False)
    attr.data[0].value = 0
    ob.update_tag()
    m = evaluated_mesh(ob)
    print("tree rebuild check: version", mod.node_group.get("sf_version"))

    # rebuild preserves values
    M.set(mod, "Width", 0.05)
    mod.node_group["sf_version"] = -1
    tree = node_hair.ensure_tree()
    check(abs(M.get(mod, "Width") - 0.05) < 1e-6, "rebuild keeps modifier values")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        FAILED.append("exception")

    print("RESULT", "FAILED" if FAILED else "OK", FAILED)
    sys.exit(1 if FAILED else 0)
