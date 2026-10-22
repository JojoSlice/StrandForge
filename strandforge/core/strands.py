"""Low-level helpers for reading and writing strands in a hair `Curves` datablock."""

from mathutils import Vector

# Attributes that must not be copied verbatim when strands are duplicated.
_SKIP_COPY = {"position", "surface_uv_coordinate"}

_VALUE_KEY = {
    "FLOAT": "value", "INT": "value", "BOOLEAN": "value", "INT8": "value",
    "FLOAT_VECTOR": "vector", "FLOAT2": "vector",
    "FLOAT_COLOR": "color", "BYTE_COLOR": "color",
}


def offsets(curves):
    return [o.value for o in curves.curve_offset_data]


def curve_points(curves, index, offs=None):
    offs = offs or offsets(curves)
    return [curves.points[i].position.copy() for i in range(offs[index], offs[index + 1])]


def selected_curves(curves):
    """Indices of selected curves. No selection attribute means everything is selected."""
    n = len(curves.curves)
    sel = curves.attributes.get(".selection")
    if sel is None:
        return list(range(n))
    vals = [bool(d.value) for d in sel.data]
    if sel.domain == "CURVE":
        return [i for i in range(n) if vals[i]]
    offs = offsets(curves)
    return [i for i in range(n) if any(vals[offs[i]:offs[i + 1]])]


def set_selection(curves, indices):
    """Select exactly `indices` (curve indices), respecting the selection domain."""
    sel = curves.attributes.get(".selection")
    if sel is None:
        sel = curves.attributes.new(".selection", "BOOLEAN", curves.selection_domain or "POINT")
    wanted = set(indices)
    if sel.domain == "CURVE":
        for i, d in enumerate(sel.data):
            d.value = i in wanted
    else:
        offs = offsets(curves)
        for c in range(len(curves.curves)):
            for p in range(offs[c], offs[c + 1]):
                sel.data[p].value = c in wanted


def ensure_curve_attr(curves, name, data_type="INT"):
    attr = curves.attributes.get(name)
    if attr is None:
        attr = curves.attributes.new(name, data_type, "CURVE")
    return attr


def add_strand(curves, points):
    """Append one curve with the given local-space points. Returns its index."""
    curves.add_curves([len(points)])
    index = len(curves.curves) - 1
    start = offsets(curves)[index]
    for i, p in enumerate(points):
        curves.points[start + i].position = p
    return index


def _attr_values(attr, start, stop):
    key = _VALUE_KEY.get(attr.data_type)
    if key is None:
        return None
    out = []
    for i in range(start, stop):
        v = getattr(attr.data[i], key)
        out.append(v.copy() if hasattr(v, "copy") else (tuple(v) if not isinstance(v, (int, float, bool)) else v))
    return key, out


def duplicate_strand(curves, index, new_points):
    """Append a copy of curve `index` with new positions, carrying over its attributes."""
    offs = offsets(curves)
    src_start, src_stop = offs[index], offs[index + 1]
    saved = []
    for attr in curves.attributes:
        if attr.name.startswith(".") or attr.name in _SKIP_COPY or attr.domain not in {"POINT", "CURVE"}:
            continue
        if attr.domain == "CURVE":
            got = _attr_values(attr, index, index + 1)
        else:
            got = _attr_values(attr, src_start, src_stop)
        if got:
            saved.append((attr.name, attr.domain, got))

    new_index = add_strand(curves, new_points)
    new_start = offsets(curves)[new_index]
    for name, domain, (key, values) in saved:
        attr = curves.attributes[name]
        base = new_index if domain == "CURVE" else new_start
        for i, v in enumerate(values):
            if domain == "POINT" and i >= len(new_points):
                break
            setattr(attr.data[base + i], key, v)
    return new_index


def resample_polyline(points, count):
    """Evenly spaced points along a polyline by arc length."""
    if len(points) < 2 or count < 2:
        return list(points)
    seg = [(points[i + 1] - points[i]).length for i in range(len(points) - 1)]
    total = sum(seg)
    if total <= 1e-9:
        return [points[0].copy() for _ in range(count)]
    out = []
    j = 0
    acc = 0.0
    for k in range(count):
        target = total * k / (count - 1)
        while j < len(seg) - 1 and acc + seg[j] < target:
            acc += seg[j]
            j += 1
        t = 0.0 if seg[j] <= 1e-12 else (target - acc) / seg[j]
        out.append(points[j].lerp(points[j + 1], min(max(t, 0.0), 1.0)))
    return out


def smooth_polyline(points, iterations, fix_first=True):
    pts = [p.copy() for p in points]
    for _ in range(iterations):
        new = [p.copy() for p in pts]
        for i in range(1, len(pts) - 1):
            new[i] = pts[i] * 0.5 + (pts[i - 1] + pts[i + 1]) * 0.25
        if not fix_first:
            new[0] = pts[0].lerp(pts[1], 0.25)
        pts = new
    return pts


def polyline_length(points):
    return sum((points[i + 1] - points[i]).length for i in range(len(points) - 1))


def closest_on_surface(head_eval, point_world):
    """(location, normal) in world space on the head mesh, or (None, None)."""
    if head_eval is None:
        return None, None
    mw = head_eval.matrix_world
    ok, loc, nor, _idx = head_eval.closest_point_on_mesh(mw.inverted() @ point_world)
    if not ok:
        return None, None
    n = (mw.to_3x3().inverted().transposed() @ nor).normalized()
    return mw @ loc, n


def fallback_normal(points):
    if len(points) >= 2:
        d = points[-1] - points[0]
        if d.length > 1e-9:
            return -d.normalized()
    return Vector((0, 0, 1))
