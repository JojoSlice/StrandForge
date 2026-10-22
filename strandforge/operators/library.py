"""User strand library: region settings saved as JSON presets.

Presets are stored in the extension's user directory so they are shared
between .blend files and survive add-on updates.
"""

import json
import os

import bpy
from bpy.props import EnumProperty, StringProperty

from ..core import modifier, project

# Inputs that reference scene data and must not travel between files.
_EXCLUDE = {"Scalp", "Material", "Viewport Detail", "Viewport Resolution", "Show Guides"}


def library_dir():
    try:
        path = bpy.utils.extension_path_user(__package__.rsplit(".", 1)[0], path="presets", create=True)
    except (ValueError, AttributeError, TypeError):
        path = os.path.join(bpy.utils.user_resource("CONFIG"), "strandforge", "presets")
        os.makedirs(path, exist_ok=True)
    return path


def list_presets():
    try:
        files = sorted(f for f in os.listdir(library_dir()) if f.endswith(".json"))
    except OSError:
        return []
    return [os.path.splitext(f)[0] for f in files]


def _items(_self, _context):
    names = list_presets()
    if not names:
        return [("NONE", "No saved presets", "")]
    return [(n, n, "") for n in names]


def _safe(name):
    return "".join(ch for ch in name if ch.isalnum() or ch in " -_").strip() or "Preset"


class SF_OT_save_user_preset(bpy.types.Operator):
    bl_idname = "strandforge.save_user_preset"
    bl_label = "Save Region as Preset"
    bl_description = "Save the active region's shape and detail settings to your StrandForge library"

    name: StringProperty(name="Name", default="My Strand")

    @classmethod
    def poll(cls, context):
        return project.active_region(context) is not None

    def invoke(self, context, _event):
        self.name = project.settings(context).user_preset_name
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        mod = modifier.find(project.active_region(context))
        values = {k: v for k, v in modifier.snapshot(mod).items() if k not in _EXCLUDE}
        path = os.path.join(library_dir(), _safe(self.name) + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"type": "strandforge.region", "version": 1, "inputs": values}, f, indent=2)
        project.settings(context).user_preset_name = self.name
        self.report({"INFO"}, f"Saved preset '{self.name}'")
        return {"FINISHED"}


class SF_OT_load_user_preset(bpy.types.Operator):
    bl_idname = "strandforge.load_user_preset"
    bl_label = "Load Preset"
    bl_description = "Apply a saved preset to the active region"
    bl_options = {"REGISTER", "UNDO"}
    bl_property = "preset"

    preset: EnumProperty(name="Preset", items=_items)

    @classmethod
    def poll(cls, context):
        return project.active_region(context) is not None

    def invoke(self, context, _event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        if self.preset == "NONE":
            return {"CANCELLED"}
        path = os.path.join(library_dir(), self.preset + ".json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            self.report({"ERROR"}, f"Could not read preset: {e}")
            return {"CANCELLED"}
        modifier.restore(modifier.find(project.active_region(context)), data.get("inputs", {}))
        self.report({"INFO"}, f"Loaded '{self.preset}'")
        return {"FINISHED"}


class SF_OT_delete_user_preset(bpy.types.Operator):
    bl_idname = "strandforge.delete_user_preset"
    bl_label = "Delete Preset"
    bl_description = "Remove a preset from your library"
    bl_property = "preset"

    preset: EnumProperty(name="Preset", items=_items)

    def invoke(self, context, _event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, _context):
        if self.preset == "NONE":
            return {"CANCELLED"}
        try:
            os.remove(os.path.join(library_dir(), self.preset + ".json"))
        except OSError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Deleted '{self.preset}'")
        return {"FINISHED"}


class SF_OT_open_library_folder(bpy.types.Operator):
    bl_idname = "strandforge.open_library_folder"
    bl_label = "Open Library Folder"
    bl_description = "Open the folder holding your presets (copy files here to share between machines)"

    def execute(self, _context):
        bpy.ops.wm.path_open(filepath=library_dir())
        return {"FINISHED"}


CLASSES = (SF_OT_save_user_preset, SF_OT_load_user_preset, SF_OT_delete_user_preset, SF_OT_open_library_folder)
