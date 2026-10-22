"""Access to Geometry Nodes modifier inputs by interface name.

Blender 5.2 exposes inputs as `mod.properties.inputs.<identifier>.value`
instead of the older `mod["Socket_N"]` ID properties.
"""

MOD_NAME = "StrandForge"


_cache = {}


def socket_map(tree):
    # Cached because panels look inputs up on every redraw; a rebuild bumps the key.
    key = (tree.as_pointer(), tree.get("sf_version"), len(tree.interface.items_tree))
    m = _cache.get(key)
    if m is None:
        m = {
            item.name: item.identifier
            for item in tree.interface.items_tree
            if item.item_type == "SOCKET" and item.in_out == "INPUT"
        }
        _cache.clear()
        _cache[key] = m
    return m


def input_struct(mod, name):
    """The RNA struct holding `.value` for an input, or None."""
    if mod is None or mod.node_group is None:
        return None
    ident = socket_map(mod.node_group).get(name)
    if ident is None:
        return None
    return getattr(mod.properties.inputs, ident, None)


def get(mod, name, default=None):
    s = input_struct(mod, name)
    return default if s is None else s.value


def set(mod, name, value):
    s = input_struct(mod, name)
    if s is None:
        return False
    s.value = value
    mod.id_data.update_tag()  # Python writes do not tag the depsgraph on their own
    return True


def snapshot(mod):
    """All input values by name (geometry inputs have no value and are skipped)."""
    values = {}
    if mod is None or mod.node_group is None:
        return values
    for name, ident in socket_map(mod.node_group).items():
        s = getattr(mod.properties.inputs, ident, None)
        if s is not None and hasattr(s, "value"):
            values[name] = s.value
    return values


def restore(mod, values):
    for name, value in values.items():
        try:
            set(mod, name, value)
        except (TypeError, ValueError, AttributeError):
            pass


def find(ob):
    """The StrandForge modifier on an object, if any."""
    if ob is None:
        return None
    for mod in ob.modifiers:
        if mod.type == "NODES" and mod.node_group and mod.node_group.name.startswith("SF_HairStrand"):
            return mod
    return None
