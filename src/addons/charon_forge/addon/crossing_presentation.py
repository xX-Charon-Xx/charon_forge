from bpy.types import Panel

from .crossing_operators import ExportShipFile, ImportShipFile


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
        import_export_row.operator(ImportShipFile.bl_idname, icon="IMPORT")
        import_export_row.operator(ExportShipFile.bl_idname, icon="EXPORT")

        # which ship's name, model and inventories a .nmsship export will carry
        crossing = context.scene.charon_crossing
        info_row = main_box.row(align=True)
        info_row.scale_y = 0.8
        if crossing.source_file:
            info_row.label(text=f"Ship data: {crossing.source_file}", icon="FILE")
        else:
            info_row.label(text="Ship data: template (empty inventories)", icon="FILE")


classes = (
    CHARON_PT_crossing_panel,
)
