"""Small helper DSL for building Geometry Nodes trees from Python."""

import math

import bpy


def _first_enabled(sockets, key):
    if isinstance(key, int):
        return sockets[key]
    for s in sockets:
        if s.enabled and (s.identifier == key or s.name == key):
            return s
    for s in sockets:
        if s.identifier == key or s.name == key:
            return s
    raise KeyError(f"socket {key!r} not found in {[s.name for s in sockets]}")


class Builder:
    def __init__(self, tree):
        self.tree = tree
        self.nodes = tree.nodes
        self.links = tree.links
        self._attr_cache = {}

    # -- low level -------------------------------------------------------
    def node(self, idname, inputs=None, label=None, **props):
        n = self.nodes.new(idname)
        for k, v in props.items():
            setattr(n, k, v)
        if label:
            n.label = label
        for key, val in (inputs or {}).items():
            self.set(n, key, val)
        return n

    def set(self, node, key, value):
        sock = _first_enabled(node.inputs, key)
        self.feed(sock, value)

    def feed(self, sock, value):
        if value is None:
            return
        if isinstance(value, bpy.types.NodeSocket):
            self.links.new(value, sock)
        elif isinstance(value, bpy.types.Node):
            self.links.new(self.out(value), sock)
        else:
            sock.default_value = value

    @staticmethod
    def out(node, key=0):
        return _first_enabled(node.outputs, key)

    # -- math ------------------------------------------------------------
    def math(self, op, a, b=None, c=None):
        n = self.node("ShaderNodeMath", operation=op)
        for i, v in enumerate((a, b, c)):
            self.feed(n.inputs[i], v)
        return n.outputs[0]

    def add(self, a, b):
        return self.math("ADD", a, b)

    def sub(self, a, b):
        return self.math("SUBTRACT", a, b)

    def mul(self, a, b):
        return self.math("MULTIPLY", a, b)

    def div(self, a, b):
        return self.math("DIVIDE", a, b)

    def madd(self, a, b, c):
        return self.math("MULTIPLY_ADD", a, b, c)

    def clamp01(self, a):
        n = self.node("ShaderNodeClamp")
        self.feed(n.inputs[0], a)
        return n.outputs[0]

    def clamp(self, a, lo, hi):
        n = self.node("ShaderNodeClamp")
        self.feed(n.inputs[0], a)
        self.feed(n.inputs[1], lo)
        self.feed(n.inputs[2], hi)
        return n.outputs[0]

    def lerp(self, a, b, f):
        n = self.node("ShaderNodeMix", data_type="FLOAT")
        self.set(n, "Factor_Float", f)
        self.set(n, "A_Float", a)
        self.set(n, "B_Float", b)
        return self.out(n, "Result")

    def map_range(self, v, fmin, fmax, tmin, tmax, interp="LINEAR", clamp=True):
        n = self.node("ShaderNodeMapRange", interpolation_type=interp, clamp=clamp)
        for i, x in enumerate((v, fmin, fmax, tmin, tmax)):
            self.feed(n.inputs[i], x)
        return n.outputs["Result"]

    def imath(self, op, a, b=None):
        n = self.node("FunctionNodeIntegerMath", operation=op)
        self.feed(n.inputs[0], a)
        self.feed(n.inputs[1], b)
        return n.outputs[0]

    def vmath(self, op, a, b=None, scale=None):
        n = self.node("ShaderNodeVectorMath", operation=op)
        self.feed(n.inputs[0], a)
        self.feed(n.inputs[1], b)
        if scale is not None:
            self.feed(n.inputs["Scale"], scale)
        if op in {"DOT_PRODUCT", "LENGTH", "DISTANCE"}:
            return n.outputs["Value"]
        return n.outputs["Vector"]

    def vadd(self, a, b):
        return self.vmath("ADD", a, b)

    def vscale(self, v, s):
        return self.vmath("SCALE", v, scale=s)

    def dot(self, a, b):
        return self.vmath("DOT_PRODUCT", a, b)

    def cross(self, a, b):
        return self.vmath("CROSS_PRODUCT", a, b)

    def normalize(self, a):
        return self.vmath("NORMALIZE", a)

    def combine(self, x=0.0, y=0.0, z=0.0):
        n = self.node("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)):
            self.feed(n.inputs[i], v)
        return n.outputs[0]

    def compare(self, op, a, b, data_type="FLOAT"):
        n = self.node("FunctionNodeCompare", data_type=data_type, operation=op)
        self.set(n, "A", a)
        self.set(n, "B", b)
        return n.outputs[0]

    def switch(self, input_type, cond, false, true):
        n = self.node("GeometryNodeSwitch", input_type=input_type)
        self.set(n, "Switch", cond)
        self.set(n, "False", false)
        self.set(n, "True", true)
        return n.outputs[0]

    def random(self, lo, hi, ident, seed, data_type="FLOAT"):
        n = self.node("FunctionNodeRandomValue", data_type=data_type)
        self.set(n, "Min", lo)
        self.set(n, "Max", hi)
        self.set(n, "ID", ident)
        self.set(n, "Seed", seed)
        return self.out(n, "Value")

    # -- attributes / geometry ---------------------------------------------
    def attr(self, name, data_type="FLOAT"):
        """Named attribute read; cached per name so the tree stays readable."""
        key = (name, data_type)
        if key not in self._attr_cache:
            n = self.node("GeometryNodeInputNamedAttribute", data_type=data_type, label=name)
            n.inputs["Name"].default_value = name
            self._attr_cache[key] = n
        return self.out(self._attr_cache[key], "Attribute")

    def attr_exists(self, name, data_type="FLOAT"):
        self.attr(name, data_type)
        return self._attr_cache[(name, data_type)].outputs["Exists"]

    def store(self, geo, name, value, data_type="FLOAT", domain="POINT"):
        n = self.node("GeometryNodeStoreNamedAttribute", data_type=data_type, domain=domain, label=name)
        self.set(n, "Geometry", geo)
        n.inputs["Name"].default_value = name
        self.set(n, "Value", value)
        return n.outputs[0]

    def input_node(self, idname, key=0):
        return self.out(self.node(idname), key)

    # -- layout ------------------------------------------------------------
    def layout(self):
        """Place nodes in columns by link depth so the tree is inspectable."""
        depth = {n.name: 0 for n in self.nodes}
        incoming = {n.name: [] for n in self.nodes}
        for link in self.links:
            incoming[link.to_node.name].append(link.from_node.name)
        changed = True
        guard = 0
        while changed and guard < 500:
            changed = False
            guard += 1
            for name, srcs in incoming.items():
                for s in srcs:
                    if depth[name] < depth[s] + 1:
                        depth[name] = depth[s] + 1
                        changed = True
        rows = {}
        for n in self.nodes:
            d = depth[n.name]
            rows.setdefault(d, 0)
            n.location = (d * 220.0, -rows[d] * 180.0)
            rows[d] += 1


TAU = math.tau
