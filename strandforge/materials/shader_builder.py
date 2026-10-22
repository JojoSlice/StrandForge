"""Base hair material: root/mid/tip gradient along `sf_v` with subtle per-strand noise."""

import bpy

DEFAULT_COLORS = (
    (0.42, 0.12, 0.22, 1.0),  # root
    (0.95, 0.45, 0.62, 1.0),  # mid
    (1.00, 0.72, 0.80, 1.0),  # tip
)


def ensure_material(name, colors=DEFAULT_COLORS):
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = colors[1]  # Solid-mode viewport color
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    bsdf.inputs["Roughness"].default_value = 0.38
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.15

    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.location = (-500, 0)
    attr.attribute_name = "sf_v"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.name = "SF_Gradient"
    ramp.label = "Root / Mid / Tip"
    ramp.location = (-300, 0)
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, colors[0]
    els[1].position, els[1].color = 1.0, colors[2]
    mid = els.new(0.35)
    mid.color = colors[1]

    nt.links.new(attr.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def gradient_node(mat):
    if mat is None or not mat.use_nodes:
        return None
    return mat.node_tree.nodes.get("SF_Gradient")


def bsdf_node(mat):
    if mat is None or not mat.use_nodes:
        return None
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    return None
