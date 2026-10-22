"""Hair projects and regions.

A project lives on the scene (character name, head mesh, collections).
Each region is one hair `Curves` object carrying the shared StrandForge
modifier, so every strand in a region shares one Geometry Nodes evaluation.
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from ..geometry import node_hair
from ..materials import shader_builder
from . import modifier
from .presets import PRESET_ORDER, STRAND_PRESETS

REGION_TYPES = (
    ("SCALP", "Scalp", "Hair lying close to the head"),
    ("BANGS", "Bangs", "Fringe and forehead hair"),
    ("SIDE_LOCKS", "Side Locks", "Locks framing the face"),
    ("BACK_HAIR", "Back Hair", "Hair behind the head"),
    ("PONYTAIL", "Ponytail", "Ponytail"),
    ("FLYAWAYS", "Flyaways", "Small loose strands"),
    ("CUSTOM", "Custom", "Custom hair group"),
)

# Starting values per region type (modifier input name -> value), applied on creation.
REGION_DEFAULTS = {
    "SCALP": {"preset": "FLAT_RIBBON", "Width": 0.035, "Strand Count": 6},
    "BANGS": {"preset": "SHARP_ANIME", "Width": 0.025, "Strand Count": 5},
    "SIDE_LOCKS": {"preset": "NATURAL_LOCK", "Width": 0.02, "Strand Count": 5},
    "BACK_HAIR": {"preset": "SOFT_CLUMP", "Width": 0.035, "Strand Count": 8},
    "PONYTAIL": {"preset": "SOFT_CLUMP", "Width": 0.03, "Strand Count": 10, "Length Segments": 48},
    "FLYAWAYS": {"preset": "FLYAWAY", "Width": 0.004, "Secondary Strands": False, "Ring Segments": 6},
    "CUSTOM": {"preset": "SOFT_CLUMP"},
}

QUALITY_LEVELS = {
    # Viewport Detail, Viewport Resolution
    "DRAFT": (0.15, 0.5),
    "PREVIEW": (0.4, 0.75),
    "FINAL": (1.0, 1.0),
}

STRAND_PRESET_ITEMS = [("REGION", "Region Settings", "Use the region's own shape settings")] + [
    (key, label, desc) for key, (label, desc, _shape) in STRAND_PRESETS.items()
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def settings(context_or_scene):
    scene = getattr(context_or_scene, "scene", context_or_scene)
    return scene.strandforge


def is_region(ob):
    return ob is not None and ob.type == "CURVES" and ob.strandforge.is_region


def active_region(context):
    ob = context.active_object
    return ob if is_region(ob) else None


def regions(scene):
    sf = scene.strandforge
    coll = sf.collection
    objs = coll.all_objects if coll else scene.objects
    return [ob for ob in objs if is_region(ob)]


def safe_name(text):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text.strip()) or "Character"


def apply_preset_to_region(mod, key):
    for name, value in STRAND_PRESETS[key][2].items():
        modifier.set(mod, name, value)


def apply_quality(scene):
    detail, res = QUALITY_LEVELS[scene.strandforge.quality]
    for ob in regions(scene):
        mod = modifier.find(ob)
        modifier.set(mod, "Viewport Detail", detail)
        modifier.set(mod, "Viewport Resolution", res)


def project_material(scene):
    sf = scene.strandforge
    if sf.material is None:
        sf.material = shader_builder.ensure_material(f"SF_{safe_name(sf.character)}_Hair")
    return sf.material


def ensure_project(scene):
    sf = scene.strandforge
    char = safe_name(sf.character)
    if sf.collection is None:
        coll = bpy.data.collections.new(f"SF_{char}_Hair")
        scene.collection.children.link(coll)
        sf.collection = coll
    project_material(scene)
    node_hair.ensure_tree()
    return sf.collection


def create_region(context, region_type, label=""):
    scene = context.scene
    sf = scene.strandforge
    coll = ensure_project(scene)
    char = safe_name(sf.character)
    label = safe_name(label) if label else dict((k, n) for k, n, _d in REGION_TYPES)[region_type].replace(" ", "")
    base = f"SF_{char}_{label}"
    name = base
    i = 1
    while name in bpy.data.objects:
        name = f"{base}_{i:02d}"
        i += 1

    data = bpy.data.hair_curves.new(name)
    data.attributes.new("sf_preset", "INT", "CURVE")
    data.attributes.new("sf_width_offset", "FLOAT", "CURVE")
    ob = bpy.data.objects.new(name, data)
    coll.objects.link(ob)
    ob.strandforge.is_region = True
    ob.strandforge.region_type = region_type

    head = sf.head
    if head is not None:
        data.surface = head
        if head.type == "MESH" and head.data.uv_layers.active:
            data.surface_uv_map = head.data.uv_layers.active.name
        ob.parent = head
        ob.matrix_parent_inverse = head.matrix_world.inverted()

    # Pre-assign the slot so Set Material reuses it instead of adding an empty slot 0.
    data.materials.append(project_material(scene))

    mod = ob.modifiers.new(modifier.MOD_NAME, "NODES")
    mod.node_group = node_hair.ensure_tree()
    modifier.set(mod, "Scalp", head)
    modifier.set(mod, "Material", project_material(scene))
    defaults = dict(REGION_DEFAULTS.get(region_type, {}))
    preset = defaults.pop("preset", None)
    if preset:
        apply_preset_to_region(mod, preset)
    for k, v in defaults.items():
        modifier.set(mod, k, v)
    detail, res = QUALITY_LEVELS[sf.quality]
    modifier.set(mod, "Viewport Detail", detail)
    modifier.set(mod, "Viewport Resolution", res)

    for other in context.view_layer.objects.selected:
        other.select_set(False)
    context.view_layer.objects.active = ob
    ob.select_set(True)
    return ob


# ---------------------------------------------------------------------------
# properties
# ---------------------------------------------------------------------------

def _quality_update(self, context):
    apply_quality(context.scene)


def _head_poll(_self, ob):
    return ob.type == "MESH"


class SF_ProjectSettings(bpy.types.PropertyGroup):
    character: StringProperty(name="Character", default="Nova")
    head: PointerProperty(name="Head Mesh", type=bpy.types.Object, poll=_head_poll,
                          description="Head or hair-cap mesh strands are attached to")
    collection: PointerProperty(name="Collection", type=bpy.types.Collection)
    material: PointerProperty(name="Material", type=bpy.types.Material)
    quality: EnumProperty(
        name="Detail Quality",
        items=(
            ("DRAFT", "Draft", "Main strands and a few secondary details"),
            ("PREVIEW", "Preview", "A representative subset of details"),
            ("FINAL", "Final", "Full generated detail"),
        ),
        default="PREVIEW",
        update=_quality_update,
        description="Viewport detail only; renders and bakes always use full detail",
    )
    ui_tab: EnumProperty(
        name="Tab",
        items=(
            ("CREATE", "Create", "", "GREASEPENCIL", 0),
            ("SHAPE", "Shape", "", "MOD_CURVE", 1),
            ("DETAIL", "Detail", "", "PARTICLES", 2),
            ("STYLE", "Style", "", "MATERIAL", 3),
            ("EXPORT", "Export", "", "EXPORT", 4),
        ),
        default="CREATE",
    )
    # Draw tool
    draw_offset: FloatProperty(name="Surface Offset", default=0.004, min=0.0, soft_max=0.05, subtype="DISTANCE",
                               description="Distance kept between drawn strands and the head surface")
    draw_smooth: IntProperty(name="Smoothing", default=3, min=0, max=30,
                             description="Smoothing iterations applied to the drawn stroke")
    draw_points: IntProperty(name="Control Points", default=0, min=0, max=64,
                             description="Control points per drawn strand (0 = automatic reduction)")
    draw_preset: EnumProperty(name="New Strand Preset", items=STRAND_PRESET_ITEMS, default="REGION",
                              description="Preset assigned to newly drawn strands")
    # Stats
    stat_triangles: IntProperty(name="Triangles", default=-1)
    stat_strands: IntProperty(name="Strands", default=-1)
    triangle_budget: IntProperty(name="Triangle Budget", default=100000, min=1000, step=1000)
    # Library
    user_preset_name: StringProperty(name="Preset Name", default="My Strand")


class SF_RegionInfo(bpy.types.PropertyGroup):
    is_region: BoolProperty(default=False)
    region_type: EnumProperty(name="Region", items=REGION_TYPES, default="CUSTOM")


CLASSES = (SF_ProjectSettings, SF_RegionInfo)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.strandforge = PointerProperty(type=SF_ProjectSettings)
    bpy.types.Object.strandforge = PointerProperty(type=SF_RegionInfo)


def unregister():
    del bpy.types.Object.strandforge
    del bpy.types.Scene.strandforge
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


def preset_attr_value(key):
    return 0 if key == "REGION" else PRESET_ORDER.index(key) + 1
