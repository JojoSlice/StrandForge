"""Builds the shared `SF_HairStrand` Geometry Nodes tree.

One tree is shared by every region object. Per-region settings live in the
modifier inputs, per-strand overrides live in curve-domain attributes:

    sf_preset        INT    0 = region settings, 1..N = built-in strand preset
    sf_width_offset  FLOAT  width multiplier is (1 + offset), so new curves default to 1x

Pipeline
    curves --(per-curve params)--> resample --(frames, width, profile)--> sweep -> primary mesh
                                        \\--> duplicate --(sample primary surface)--> sweep -> secondary mesh

Internal attributes use the `sfc_` (curve) and `sfp_` (point) prefixes and are
removed before output. `sf_v` (0 at root, 1 at tip) and `UVMap` are kept for
materials and export.
"""

import math

import bpy

from ..core import modifier
from ..core.presets import PRESET_ORDER, SHAPE_PARAMS, STRAND_PRESETS
from .builder import TAU, Builder

TREE_NAME = "SF_HairStrand"
TREE_VERSION = 2

PI = math.pi

# (panel, name, socket type, default, min, max, subtype)
INPUTS = (
    ("Primary", "Scalp", "NodeSocketObject", None, None, None, None),
    ("Primary", "Material", "NodeSocketMaterial", None, None, None, None),
    ("Primary", "Width", "NodeSocketFloat", 0.03, 0.0, 10.0, "DISTANCE"),
    ("Primary", "Width Variation", "NodeSocketFloat", 0.15, 0.0, 1.0, "FACTOR"),
    ("Primary", "Thickness Ratio", "NodeSocketFloat", 0.55, 0.02, 2.0, None),
    ("Primary", "Root Width", "NodeSocketFloat", 0.6, 0.0, 1.0, "FACTOR"),
    ("Primary", "Peak Position", "NodeSocketFloat", 0.35, 0.01, 0.99, "FACTOR"),
    ("Primary", "Tip Width", "NodeSocketFloat", 0.0, 0.0, 1.0, "FACTOR"),
    ("Primary", "Taper Power", "NodeSocketFloat", 1.4, 0.1, 8.0, None),
    ("Primary", "Close Root", "NodeSocketBool", True, None, None, None),
    ("Profile", "Root Sharpness", "NodeSocketFloat", 2.0, 0.5, 8.0, None),
    ("Profile", "Root Teardrop", "NodeSocketFloat", 0.1, 0.0, 1.0, "FACTOR"),
    ("Profile", "Root Asymmetry", "NodeSocketFloat", 0.0, -1.0, 1.0, None),
    ("Profile", "Root Flatten", "NodeSocketFloat", 0.3, 0.0, 1.0, "FACTOR"),
    ("Profile", "Tip Sharpness", "NodeSocketFloat", 2.0, 0.5, 8.0, None),
    ("Profile", "Tip Teardrop", "NodeSocketFloat", 0.2, 0.0, 1.0, "FACTOR"),
    ("Profile", "Tip Asymmetry", "NodeSocketFloat", 0.0, -1.0, 1.0, None),
    ("Profile", "Tip Flatten", "NodeSocketFloat", 0.2, 0.0, 1.0, "FACTOR"),
    ("Profile", "Profile Rotation", "NodeSocketFloat", 0.0, -PI, PI, "ANGLE"),
    ("Profile", "Twist", "NodeSocketFloat", 0.0, -10.0, 10.0, None),
    ("Profile", "Roll Variation", "NodeSocketFloat", 0.0, 0.0, PI, "ANGLE"),
    ("Profile", "Align to Scalp", "NodeSocketBool", True, None, None, None),
    ("Resolution", "Length Segments", "NodeSocketInt", 32, 3, 512, None),
    ("Resolution", "Ring Segments", "NodeSocketInt", 12, 3, 64, None),
    ("Secondary", "Secondary Strands", "NodeSocketBool", True, None, None, None),
    ("Secondary", "Strand Count", "NodeSocketInt", 8, 0, 500, None),
    ("Secondary", "Width Min", "NodeSocketFloat", 0.15, 0.01, 1.0, "FACTOR"),
    ("Secondary", "Width Max", "NodeSocketFloat", 0.35, 0.01, 1.0, "FACTOR"),
    ("Secondary", "Length Min", "NodeSocketFloat", 0.4, 0.01, 1.0, "FACTOR"),
    ("Secondary", "Length Max", "NodeSocketFloat", 0.85, 0.01, 1.0, "FACTOR"),
    ("Secondary", "Root Bias", "NodeSocketFloat", 0.05, 0.0, 1.0, "FACTOR"),
    ("Secondary", "Tip Bias", "NodeSocketFloat", 0.95, 0.0, 1.0, "FACTOR"),
    ("Secondary", "Coverage", "NodeSocketFloat", 0.45, 0.0, 1.0, "FACTOR"),
    ("Secondary", "Surface Offset", "NodeSocketFloat", 0.35, -1.0, 1.0, None),
    ("Secondary", "Secondary Thickness", "NodeSocketFloat", 0.6, 0.05, 2.0, None),
    ("Secondary", "Flow Variation", "NodeSocketFloat", 0.2, 0.0, 2.0, None),
    ("Secondary", "Flow Frequency", "NodeSocketFloat", 1.2, 0.1, 20.0, None),
    ("Secondary", "Secondary Length Segments", "NodeSocketInt", 16, 3, 256, None),
    ("Secondary", "Secondary Ring Segments", "NodeSocketInt", 6, 3, 32, None),
    ("Secondary", "Seed", "NodeSocketInt", 0, 0, 100000, None),
    ("Quality", "Viewport Detail", "NodeSocketFloat", 1.0, 0.0, 1.0, "FACTOR"),
    ("Quality", "Viewport Resolution", "NodeSocketFloat", 1.0, 0.1, 1.0, "FACTOR"),
    ("Quality", "Show Guides", "NodeSocketBool", False, None, None, None),
)

INPUT_NAMES = tuple(i[1] for i in INPUTS)

# Profile used for every secondary strand: (sharpness, teardrop, asymmetry, flatten)
SECONDARY_PROFILE = (2.2, 0.15, 0.0, 0.4)


# ---------------------------------------------------------------------------
# interface
# ---------------------------------------------------------------------------

def _build_interface(tree):
    iface = tree.interface
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    panels = {}
    for panel, name, stype, default, lo, hi, subtype in INPUTS:
        if panel not in panels:
            panels[panel] = iface.new_panel(panel, default_closed=panel != "Primary")
        sock = iface.new_socket(name, in_out="INPUT", socket_type=stype, parent=panels[panel])
        if subtype and hasattr(sock, "subtype"):
            try:
                sock.subtype = subtype
            except (TypeError, AttributeError):
                pass
        if default is not None:
            sock.default_value = default
        if lo is not None:
            sock.min_value = lo
            sock.max_value = hi


# ---------------------------------------------------------------------------
# field macros (generate nodes inline)
# ---------------------------------------------------------------------------

class _Ctx:
    def __init__(self, b, gi):
        self.b = b
        self.gi = gi

    def inp(self, name):
        return self.gi.outputs[name]


def _profile_xy(b, theta, sharp, tear, asym, flat):
    """Superellipse cross-section with teardrop, asymmetry and flat underside."""
    c = b.math("COSINE", theta)
    s = b.math("SINE", theta)
    e = b.div(2.0, b.math("MAXIMUM", sharp, 0.1))
    x = b.mul(b.math("SIGN", c), b.math("POWER", b.math("ABSOLUTE", c), e))
    y = b.mul(b.math("SIGN", s), b.math("POWER", b.math("ABSOLUTE", s), e))
    # teardrop: narrow towards +x
    y = b.mul(y, b.sub(1.0, b.mul(tear, b.madd(x, 0.5, 0.5))))
    # asymmetry: one side wider than the other
    x = b.mul(x, b.madd(asym, b.math("SIGN", x), 1.0))
    # flatten underside (towards scalp)
    y = b.mul(y, b.sub(1.0, b.mul(flat, b.math("LESS_THAN", y, 0.0))))
    return x, y


def _width_factor(b, v):
    """Width multiplier along the strand from per-curve taper attributes."""
    rw = b.attr("sfc_root_width")
    pk = b.attr("sfc_peak")
    tw = b.attr("sfc_tip_width")
    tp = b.attr("sfc_taper")
    rise = b.map_range(v, 0.0, pk, rw, 1.0, interp="SMOOTHSTEP")
    t = b.map_range(v, pk, 1.0, 0.0, 1.0)
    fall = b.sub(1.0, b.mul(b.sub(1.0, tw), b.math("POWER", t, tp)))
    return b.switch("FLOAT", b.compare("LESS_THAN", v, pk), fall, rise)


def _half_sizes(ctx, v, close_root=True):
    """Half width / half thickness of the primary strand at factor v."""
    b = ctx.b
    f = _width_factor(b, v)
    w = b.mul(b.mul(b.attr("sfc_width"), 0.5), f)
    if close_root:
        closed = b.node("FunctionNodeBooleanMath", operation="AND")
        b.feed(closed.inputs[0], ctx.inp("Close Root"))
        b.feed(closed.inputs[1], b.compare("LESS_THAN", v, 1e-4))
        w = b.switch("FLOAT", closed.outputs[0], w, 0.0)
    t = b.mul(w, b.attr("sfc_thickness"))
    return w, t


def _profile_params(b, v):
    fac = b.map_range(v, 0.0, 1.0, 0.0, 1.0, interp="SMOOTHSTEP")
    return tuple(
        b.lerp(b.attr(f"sfc_root_{k}"), b.attr(f"sfc_tip_{k}"), fac)
        for k in ("sharp", "tear", "asym", "flat")
    )


def _frame(b, tangent, normal0, angle):
    """Rotate the minimum-twist frame around the tangent. Returns (up, side)."""
    side0 = b.cross(tangent, normal0)
    up = b.vadd(b.vscale(normal0, b.math("COSINE", angle)), b.vscale(side0, b.math("SINE", angle)))
    side = b.cross(tangent, up)
    return up, side


def _roll_angle(b, v):
    twist = b.mul(b.mul(b.attr("sfc_twist"), TAU), v)
    return b.add(b.add(b.attr("sfc_align"), b.attr("sfc_roll")), twist)


def _sweep(ctx, curves, ring_count):
    """Custom sweep: ring topology from Curve to Mesh, positions from sfp_* attributes."""
    b = ctx.b
    line = b.node("GeometryNodeCurvePrimitiveLine", inputs={"Start": (0, 0, 0), "End": (1, 0, 0)})
    prof = b.node("GeometryNodeResampleCurve", inputs={"Curve": line, "Count": b.imath("ADD", ring_count, 1)})
    pu = b.input_node("GeometryNodeSplineParameter", "Factor")
    prof_geo = b.store(prof.outputs[0], "sfp_pu", pu)

    c2m = b.node("GeometryNodeCurveToMesh", inputs={"Curve": curves, "Profile Curve": prof_geo, "Fill Caps": False})

    pu_attr = b.attr("sfp_pu")
    theta = b.sub(b.mul(pu_attr, TAU), PI * 0.5)  # seam on the underside
    x, y = _profile_xy(b, theta, b.attr("sfp_sharp"), b.attr("sfp_tear"), b.attr("sfp_asym"), b.attr("sfp_flat"))
    pos = b.vadd(
        b.attr("sfp_center", "FLOAT_VECTOR"),
        b.vadd(
            b.vscale(b.attr("sfp_side", "FLOAT_VECTOR"), b.mul(x, b.attr("sfp_w"))),
            b.vscale(b.attr("sfp_up", "FLOAT_VECTOR"), b.mul(y, b.attr("sfp_t"))),
        ),
    )
    mesh = b.node("GeometryNodeSetPosition", inputs={"Geometry": c2m, "Position": pos}).outputs[0]
    uv = b.combine(pu_attr, b.attr("sf_v"), 0.0)
    return b.store(mesh, "UVMap", uv, data_type="FLOAT2", domain="CORNER")


def _store_many(b, geo, items, domain):
    for name, value, dtype in items:
        geo = b.store(geo, name, value, data_type=dtype, domain=domain)
    return geo


def _detail_fraction(ctx, name):
    """Viewport-only reduction (Draft/Preview); renders and exports use 1.0."""
    b = ctx.b
    is_vp = b.input_node("GeometryNodeIsViewport")
    return b.switch("FLOAT", is_vp, 1.0, ctx.inp(name))


# ---------------------------------------------------------------------------
# main graph
# ---------------------------------------------------------------------------

def _build_primary_params(ctx, geo):
    """Resolve region inputs / per-strand presets into curve-domain attributes."""
    b = ctx.b
    preset = b.attr("sf_preset", "INT")
    index = b.imath("MINIMUM", b.imath("MAXIMUM", preset, 0), len(PRESET_ORDER))

    resolved = {}
    for param in SHAPE_PARAMS:
        sw = b.node("GeometryNodeIndexSwitch", data_type="FLOAT", label=param)
        while len(sw.index_switch_items) < len(PRESET_ORDER) + 1:
            sw.index_switch_items.new()
        b.set(sw, "Index", index)
        b.set(sw, "Item_0", ctx.inp(param))
        for i, key in enumerate(PRESET_ORDER, start=1):
            b.set(sw, f"Item_{i}", STRAND_PRESETS[key][2][param])
        resolved[param] = sw.outputs[0]

    curve_index = b.input_node("GeometryNodeInputIndex")
    seed = ctx.inp("Seed")
    width_rand = b.random(-1.0, 1.0, curve_index, b.imath("ADD", seed, 11))
    width_offset = b.attr("sf_width_offset")
    width = b.mul(
        ctx.inp("Width"),
        b.mul(b.add(1.0, width_offset), b.madd(width_rand, ctx.inp("Width Variation"), 1.0)),
    )
    roll = b.madd(b.random(-1.0, 1.0, curve_index, b.imath("ADD", seed, 13)), ctx.inp("Roll Variation"),
                  ctx.inp("Profile Rotation"))

    items = [
        ("sfc_id", curve_index, "INT"),
        ("sfc_width", width, "FLOAT"),
        ("sfc_thickness", resolved["Thickness Ratio"], "FLOAT"),
        ("sfc_root_width", resolved["Root Width"], "FLOAT"),
        ("sfc_peak", b.clamp(resolved["Peak Position"], 0.01, 0.99), "FLOAT"),
        ("sfc_tip_width", resolved["Tip Width"], "FLOAT"),
        ("sfc_taper", resolved["Taper Power"], "FLOAT"),
        ("sfc_twist", resolved["Twist"], "FLOAT"),
        ("sfc_roll", roll, "FLOAT"),
    ]
    for end in ("Root", "Tip"):
        low = end.lower()
        items += [
            (f"sfc_{low}_sharp", resolved[f"{end} Sharpness"], "FLOAT"),
            (f"sfc_{low}_tear", resolved[f"{end} Teardrop"], "FLOAT"),
            (f"sfc_{low}_asym", resolved[f"{end} Asymmetry"], "FLOAT"),
            (f"sfc_{low}_flat", resolved[f"{end} Flatten"], "FLOAT"),
        ]
    return _store_many(b, geo, items, "CURVE")


def _root_alignment(ctx, geo):
    """Per-curve angle that turns the minimum-twist normal towards the scalp normal at the root."""
    b = ctx.b
    info = b.node("GeometryNodeObjectInfo", transform_space="RELATIVE", inputs={"Object": ctx.inp("Scalp")})
    sample = b.node("GeometryNodeSampleNearestSurface", data_type="FLOAT_VECTOR")
    b.set(sample, "Mesh", info.outputs["Geometry"])
    b.set(sample, "Value", b.input_node("GeometryNodeInputNormal"))
    b.set(sample, "Sample Position", b.input_node("GeometryNodeInputPosition"))
    valid = b.node("FunctionNodeBooleanMath", operation="AND")
    b.feed(valid.inputs[0], b.out(sample, "Is Valid"))
    b.feed(valid.inputs[1], ctx.inp("Align to Scalp"))
    up_ref = b.switch("VECTOR", valid.outputs[0], (0.0, 0.0, 1.0), b.out(sample, "Value"))

    tangent = b.input_node("GeometryNodeInputTangent")
    normal0 = b.input_node("GeometryNodeInputNormal")
    proj = b.vmath("SUBTRACT", up_ref, b.vscale(tangent, b.dot(tangent, up_ref)))
    sin_a = b.dot(b.cross(normal0, proj), tangent)
    cos_a = b.dot(normal0, proj)
    angle = b.math("ARCTAN2", sin_a, cos_a)

    root_point = b.node("GeometryNodePointsOfCurve", inputs={"Sort Index": 0})
    at_root = b.node("GeometryNodeFieldAtIndex", data_type="FLOAT", domain="POINT")
    b.set(at_root, "Value", angle)
    b.set(at_root, "Index", b.out(root_point, "Point Index"))
    return b.store(geo, "sfc_align", at_root.outputs[0], domain="CURVE")


def _primary_point_attrs(ctx, geo):
    b = ctx.b
    v = b.input_node("GeometryNodeSplineParameter", "Factor")
    tangent = b.input_node("GeometryNodeInputTangent")
    normal0 = b.input_node("GeometryNodeInputNormal")
    up, side = _frame(b, tangent, normal0, _roll_angle(b, v))
    w, t = _half_sizes(ctx, v)
    sharp, tear, asym, flat = _profile_params(b, v)
    items = [
        ("sf_v", v, "FLOAT"),
        ("sfp_center", b.input_node("GeometryNodeInputPosition"), "FLOAT_VECTOR"),
        ("sfp_up", up, "FLOAT_VECTOR"),
        ("sfp_side", side, "FLOAT_VECTOR"),
        ("sfp_w", w, "FLOAT"),
        ("sfp_t", t, "FLOAT"),
        ("sfp_sharp", sharp, "FLOAT"),
        ("sfp_tear", tear, "FLOAT"),
        ("sfp_asym", asym, "FLOAT"),
        ("sfp_flat", flat, "FLOAT"),
    ]
    return _store_many(b, geo, items, "POINT")


def _secondary(ctx, prim):
    """Smaller strands placed in the primary's (v, angle) surface coordinates."""
    b = ctx.b
    fraction = _detail_fraction(ctx, "Viewport Detail")
    count = b.math("ROUND", b.mul(ctx.inp("Strand Count"), fraction))
    dup = b.node("GeometryNodeDuplicateElements", domain="SPLINE")
    b.set(dup, "Geometry", prim)
    b.set(dup, "Selection", ctx.inp("Secondary Strands"))
    b.set(dup, "Amount", count)
    geo = b.store(dup.outputs["Geometry"], "sfc_dup", dup.outputs["Duplicate Index"], data_type="INT", domain="CURVE")

    res_frac = _detail_fraction(ctx, "Viewport Resolution")
    seg = b.math("MAXIMUM", b.math("ROUND", b.mul(ctx.inp("Secondary Length Segments"), res_frac)), 3.0)
    geo = b.node("GeometryNodeResampleCurve", inputs={"Curve": geo, "Count": seg}).outputs[0]

    u = b.input_node("GeometryNodeSplineParameter", "Factor")
    ident = b.imath("ADD", b.imath("MULTIPLY", b.attr("sfc_id", "INT"), 7919), b.attr("sfc_dup", "INT"))
    seed = ctx.inp("Seed")

    def rnd(lo, hi, k):
        return b.random(lo, hi, ident, b.imath("ADD", seed, k))

    r_theta = rnd(-1.0, 1.0, 1)
    theta_k = b.madd(b.mul(r_theta, ctx.inp("Coverage")), PI, PI * 0.5)
    root_bias = ctx.inp("Root Bias")
    tip_bias = ctx.inp("Tip Bias")
    v0 = b.madd(rnd(0.0, 1.0, 2), b.mul(b.sub(tip_bias, root_bias), 0.5), root_bias)
    v1 = b.math("MINIMUM", b.add(v0, rnd(ctx.inp("Length Min"), ctx.inp("Length Max"), 3)), tip_bias)
    vs = b.lerp(v0, v1, u)

    noise = b.node("ShaderNodeTexNoise", noise_dimensions="1D")
    b.set(noise, "W", b.madd(u, ctx.inp("Flow Frequency"), b.mul(r_theta, 37.0)))
    b.set(noise, "Detail", 0.0)
    drift = b.mul(b.mul(b.sub(b.out(noise, "Factor"), 0.5), 2.0), ctx.inp("Flow Variation"))
    theta = b.add(theta_k, drift)

    sample = b.node("GeometryNodeSampleCurve", mode="FACTOR", use_all_curves=False)
    b.set(sample, "Curves", prim)
    b.set(sample, "Factor", vs)
    b.set(sample, "Curve Index", b.attr("sfc_id", "INT"))
    pos = b.out(sample, "Position")
    tangent = b.out(sample, "Tangent")
    up, side = _frame(b, tangent, b.out(sample, "Normal"), _roll_angle(b, vs))
    w, t = _half_sizes(ctx, vs, close_root=False)
    x, y = _profile_xy(b, theta, *_profile_params(b, vs))

    surface = b.vadd(pos, b.vadd(b.vscale(side, b.mul(x, w)), b.vscale(up, b.mul(y, t))))
    outward = b.normalize(b.vadd(b.vscale(side, b.mul(x, t)), b.vscale(up, b.mul(y, w))))

    shape = b.mul(b.map_range(u, 0.0, 0.15, 0.0, 1.0, interp="SMOOTHSTEP"),
                  b.math("POWER", b.sub(1.0, u), 0.7))
    ws = b.mul(b.mul(rnd(ctx.inp("Width Min"), ctx.inp("Width Max"), 4), w), shape)
    ts = b.mul(ws, ctx.inp("Secondary Thickness"))
    lift = b.madd(rnd(-1.0, 1.0, 5), 0.15, ctx.inp("Surface Offset"))
    center = b.vadd(surface, b.vscale(outward, b.mul(ts, lift)))
    sec_side = b.normalize(b.cross(tangent, outward))

    sp = SECONDARY_PROFILE
    items = [
        ("sf_v", vs, "FLOAT"),
        ("sfp_center", center, "FLOAT_VECTOR"),
        ("sfp_up", outward, "FLOAT_VECTOR"),
        ("sfp_side", sec_side, "FLOAT_VECTOR"),
        ("sfp_w", ws, "FLOAT"),
        ("sfp_t", ts, "FLOAT"),
        ("sfp_sharp", sp[0], "FLOAT"),
        ("sfp_tear", sp[1], "FLOAT"),
        ("sfp_asym", sp[2], "FLOAT"),
        ("sfp_flat", sp[3], "FLOAT"),
    ]
    geo = _store_many(b, geo, items, "POINT")
    return _sweep(ctx, geo, ctx.inp("Secondary Ring Segments"))


def build(tree):
    tree.nodes.clear()
    tree.interface.clear()
    _build_interface(tree)
    b = Builder(tree)
    gi = b.node("NodeGroupInput")
    go = b.node("NodeGroupOutput")
    ctx = _Ctx(b, gi)

    geo = gi.outputs["Geometry"]
    guides = geo
    geo = _build_primary_params(ctx, geo)

    res_frac = _detail_fraction(ctx, "Viewport Resolution")
    seg = b.math("MAXIMUM", b.math("ROUND", b.mul(ctx.inp("Length Segments"), res_frac)), 3.0)
    geo = b.node("GeometryNodeResampleCurve", inputs={"Curve": geo, "Count": seg}).outputs[0]
    geo = b.node("GeometryNodeSetCurveNormal", inputs={"Curve": geo, "Mode": "Minimum Twist"}).outputs[0]
    geo = _root_alignment(ctx, geo)
    prim = _primary_point_attrs(ctx, geo)

    prim_mesh = _sweep(ctx, prim, ctx.inp("Ring Segments"))
    sec_mesh = _secondary(ctx, prim)

    join = b.node("GeometryNodeJoinGeometry")
    b.links.new(sec_mesh, join.inputs[0])
    b.links.new(prim_mesh, join.inputs[0])
    mesh = b.node("GeometryNodeMergeByDistance", inputs={"Geometry": join, "Mode": "All", "Distance": 1e-6})
    mesh = b.node("GeometryNodeSetShadeSmooth", inputs={"Geometry": mesh, "Shade Smooth": True})
    mesh = b.node("GeometryNodeSetMaterial", inputs={"Geometry": mesh, "Material": ctx.inp("Material")})
    for pattern in ("sfp_*", "sfc_*", "sf_preset", "sf_width_offset"):
        mode = "Wildcard" if "*" in pattern else "Exact"
        mesh = b.node("GeometryNodeRemoveAttribute", inputs={"Geometry": mesh, "Pattern Mode": mode,
                                                             "Name": pattern})

    show = b.node("GeometryNodeSwitch", input_type="GEOMETRY")
    b.set(show, "Switch", ctx.inp("Show Guides"))
    final_join = b.node("GeometryNodeJoinGeometry")
    b.links.new(guides, final_join.inputs[0])
    b.set(show, "True", final_join)
    b.links.new(b.out(mesh), final_join.inputs[0])
    b.set(show, "False", mesh)
    b.set(go, "Geometry", show)

    b.layout()
    tree["sf_version"] = TREE_VERSION
    return tree


# ---------------------------------------------------------------------------
# public helpers
# ---------------------------------------------------------------------------

def _users(tree):
    for ob in bpy.data.objects:
        for mod in ob.modifiers:
            if mod.type == "NODES" and mod.node_group == tree:
                yield mod


def ensure_tree():
    """Get the shared tree, (re)building it when missing or outdated.

    Modifier values are carried over by input name across rebuilds.
    """
    tree = bpy.data.node_groups.get(TREE_NAME)
    if tree is not None and tree.get("sf_version") == TREE_VERSION:
        return tree
    saved = []
    if tree is None:
        tree = bpy.data.node_groups.new(TREE_NAME, "GeometryNodeTree")
    else:
        saved = [(mod, modifier.snapshot(mod)) for mod in _users(tree)]
    build(tree)
    for mod, values in saved:
        mod.node_group = tree
        modifier.restore(mod, values)
    return tree
