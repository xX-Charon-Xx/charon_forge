from bpy.types import Panel

from .crossing_operators import ExportNmsShip, ImportNmsShip


# Crossing Panel ---
class CHARON_PT_crossing_panel(Panel):
    bl_idname = "CHARON_PT_crossing_panel"
    bl_label = "Crossing"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Charon Forge"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout
        main_box = layout.column(align=True)

        import_export_row = main_box.row(align=True)
        import_export_row.operator(ImportNmsShip.bl_idname)
        import_export_row.operator(ExportNmsShip.bl_idname)


classes = (
    CHARON_PT_crossing_panel,
)
