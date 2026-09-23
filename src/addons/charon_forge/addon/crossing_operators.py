import bpy


class ImportNmsShip(bpy.types.Operator):
    """Import a .nmsship file (dummy)"""

    bl_idname = "object.charon_import_nmsship"
    bl_label = "Import .nmsship"

    def execute(self, context):
        self.report({"INFO"}, "Import .nmsship (dummy)")
        return {"FINISHED"}


class ExportNmsShip(bpy.types.Operator):
    """Export as a .nmsship file (dummy)"""

    bl_idname = "object.charon_export_nmsship"
    bl_label = "Export as .nmsship"

    def execute(self, context):
        self.report({"INFO"}, "Export as .nmsship (dummy)")
        return {"FINISHED"}


classes = (
    ImportNmsShip,
    ExportNmsShip,
)
