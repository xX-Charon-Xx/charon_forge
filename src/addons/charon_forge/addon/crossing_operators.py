import json
import os

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper

from ..builder import importer
from ..utils import loading_overlay, nmsship

EXPORT_FORMATS = [
    (nmsship.FORMAT_NMSSHIP, ".nmsship", "A corvette with its ship record and customisation (zip)"),
    (nmsship.FORMAT_JSON, ".json", "Just the parts, as {\"Objects\": [...]}"),
]


class ImportShipFile(bpy.types.Operator, ImportHelper):
    """Import a ship into the scene from a .nmsship, .json or .txt file"""

    bl_idname = "object.charon_import_nmsship"
    bl_label = "Import File"
    bl_options = {"REGISTER", "UNDO"}

    filter_glob: bpy.props.StringProperty(
        default="*.nmsship;*.json;*.txt", options={"HIDDEN", "SKIP_SAVE"}
    )

    @loading_overlay.while_running("Importing ship")
    def execute(self, context):
        from ..builder import get_builder

        file_name = os.path.basename(self.filepath)
        try:
            objects, ship, customisation, base_version = nmsship.read_any(self.filepath)
        except nmsship.NmsShipError as error:
            self.report({"ERROR"}, f"Could not import {file_name}: {error}")
            return {"CANCELLED"}

        # the file is read first, so a bad one leaves the scene as it was
        importer.clear_scene_parts(context.scene)

        # the file's own BaseVersion, so an older export is placed the way it
        # was built
        get_builder().deserialise_from_data(
            {"Objects": objects, "BaseVersion": base_version}
        )

        # a .nmsship's ship record and customisation are kept for Export,
        # which writes them back out around the scene's parts. A .json/.txt
        # has none, so whatever was kept before stays.
        if ship is not None:
            context.scene.charon_crossing.store_ship(ship, customisation, file_name)

        self.report({"INFO"}, f"Imported {len(objects)} part(s) from {file_name}")
        return {"FINISHED"}


class ExportShipFile(bpy.types.Operator, ExportHelper):
    """Export the scene's parts as a .nmsship corvette or a .json parts file"""

    bl_idname = "object.charon_export_nmsship"
    bl_label = "Export File"

    filename_ext = ".nmsship"
    filter_glob: bpy.props.StringProperty(default="*.nmsship;*.json", options={"HIDDEN", "SKIP_SAVE"})

    file_format: bpy.props.EnumProperty(
        name="Format",
        description="What kind of file to write",
        items=EXPORT_FORMATS,
        default=nmsship.FORMAT_NMSSHIP,
    )

    ship_name: bpy.props.StringProperty(
        name="Ship Name",
        description="The corvette's name in game",
    )

    def _sync_extension(self):
        # ExportHelper appends filename_ext to the path as the user types,
        # so it has to follow the format picked
        self.filename_ext = nmsship.EXTENSIONS[self.file_format]

    def invoke(self, context, event):
        stored = context.scene.charon_crossing.get_ship()
        ship, _ = stored if stored is not None else nmsship.load_template()
        self.ship_name = ship.get("Name", "")
        self._sync_extension()
        return super().invoke(context, event)

    def check(self, context):
        self._sync_extension()
        return super().check(context)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "file_format", expand=True)
        if self.file_format != nmsship.FORMAT_NMSSHIP:
            return

        layout.prop(self, "ship_name")
        crossing = context.scene.charon_crossing
        if crossing.get_ship() is not None:
            layout.label(text=f"Ship data from {crossing.source_file}", icon="INFO")
        else:
            layout.label(text="No ship imported, empty inventories", icon="INFO")

    @loading_overlay.while_running("Exporting ship")
    def execute(self, context):
        from ..builder import get_builder

        objects = get_builder().serialise().get("Objects", [])
        if not objects:
            self.report({"WARNING"}, "There are no parts in the scene to export")
            return {"CANCELLED"}

        # swap the other format's extension rather than stacking this one on
        self._sync_extension()
        base, extension = os.path.splitext(self.filepath)
        if extension.lower() in nmsship.EXTENSIONS.values():
            filepath = base + self.filename_ext
        else:
            filepath = bpy.path.ensure_ext(self.filepath, self.filename_ext)

        try:
            if self.file_format == nmsship.FORMAT_JSON:
                nmsship.write_json(filepath, objects)
            else:
                stored = context.scene.charon_crossing.get_ship()
                ship, customisation = stored if stored is not None else nmsship.load_template()
                if self.ship_name.strip():
                    ship["Name"] = self.ship_name.strip()
                nmsship.write(filepath, objects, ship, customisation)
        except OSError as error:
            self.report({"ERROR"}, f"Could not write the file: {error}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Exported {len(objects)} part(s) to {os.path.basename(filepath)}")
        return {"FINISHED"}


class ImportShipClipboard(bpy.types.Operator):
    """Import a ship's parts from JSON on the clipboard - an array of parts,
    or an object holding them in Objects"""

    bl_idname = "object.charon_import_clipboard"
    bl_label = "Import from Clipboard"
    bl_options = {"REGISTER", "UNDO"}

    @loading_overlay.while_running("Importing from the clipboard")
    def execute(self, context):
        from ..builder import get_builder

        try:
            objects, base_version = nmsship.read_parts_text(context.window_manager.clipboard)
        except nmsship.NmsShipError as error:
            self.report({"ERROR"}, f"Could not import from the clipboard: {error}")
            return {"CANCELLED"}

        # the clipboard is read first, so bad data leaves the scene as it was
        importer.clear_scene_parts(context.scene)

        get_builder().deserialise_from_data(
            {"Objects": objects, "BaseVersion": base_version}
        )
        self.report({"INFO"}, f"Imported {len(objects)} part(s) from the clipboard")
        return {"FINISHED"}


class ExportShipClipboard(bpy.types.Operator):
    """Copy the scene's parts to the clipboard as JSON - just the parts, or
    the whole base with Objects Only off"""

    bl_idname = "object.charon_export_clipboard"
    bl_label = "Export to Clipboard"

    @loading_overlay.while_running("Copying to the clipboard")
    def execute(self, context):
        from ..builder import get_builder

        data = get_builder().serialise()
        objects = data.get("Objects", [])
        if not objects:
            self.report({"WARNING"}, "There are no parts in the scene to export")
            return {"CANCELLED"}

        if context.scene.charon_crossing.clipboard_objects_only:
            # a bare array, the way the base builder addon's Objects Only does
            export = objects
        else:
            # the whole base, with its properties, when the base builder
            # addon holds them (scene.nms_base_tool, filled on import)
            base_tool = getattr(context.scene, "nms_base_tool", None)
            try:
                export = base_tool.serialise() if base_tool is not None else None
            except Exception as error:                        # noqa: BLE001
                print("Charon Forge: could not serialise the base:", error)
                export = None
            if export is None:
                export = {"Objects": objects, "BaseVersion": data.get("BaseVersion", 8)}

        context.window_manager.clipboard = json.dumps(export, indent=2, ensure_ascii=False)
        self.report({"INFO"}, f"Copied {len(objects)} part(s) to the clipboard")
        return {"FINISHED"}


classes = (
    ImportShipFile,
    ExportShipFile,
    ImportShipClipboard,
    ExportShipClipboard,
)
