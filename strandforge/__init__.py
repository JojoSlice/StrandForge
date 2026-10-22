"""StrandForge – stylized mesh hair from curves with procedural detail."""

import bpy

from .core import project
from .operators import create_hair, draw_strand, export_asset, library, strand_ops
from .ui import panels

_MODULE_CLASSES = (
    create_hair.CLASSES
    + strand_ops.CLASSES
    + draw_strand.CLASSES
    + library.CLASSES
    + export_asset.CLASSES
    + panels.CLASSES
)

_keymaps = []


def _register_keymaps():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:  # background mode
        return
    km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
    kmi = km.keymap_items.new("wm.call_menu", "W", "PRESS", alt=True)
    kmi.properties.name = panels.VIEW3D_MT_strandforge_quick.bl_idname
    _keymaps.append((km, kmi))


def register():
    project.register()
    for cls in _MODULE_CLASSES:
        bpy.utils.register_class(cls)
    _register_keymaps()


def unregister():
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
    for cls in reversed(_MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
    project.unregister()
