import os

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper

from ..utils import nmsship

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

    def execute(self, context):
        from ..builder import get_builder

        file_name = os.path.basename(self.filepath)
        try:
            objects, ship, customisation, base_version = nmsship.read_any(self.filepath)
        except nmsship.NmsShipError as error:
            self.report({"ERROR"}, f"Could not import {file_name}: {error}")
            return {"CANCELLED"}

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


classes = (
    ImportShipFile,
    ExportShipFile,
)
