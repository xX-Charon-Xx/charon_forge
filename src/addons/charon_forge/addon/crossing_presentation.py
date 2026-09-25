from bpy.types import Panel

from ..utils import icon_utils
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

        # laid out like the optimiser panel: the icon on the left, the
        # description and buttons in a column beside it
        description_row = layout.row(align = True)
        description_row.scale_y = 0.6
        description_icon_row = description_row.row(align = True)
        description_icon_row.scale_x = 1.1
        description_icon_row.template_icon(
            icon_value=icon_utils.get_icon_id("crossing"),
            scale=3,
        )
        description_column = description_row.column(align=True)
        description_column.separator()
        description_column.label(text="Import and export ships as")
        description_column.label(text=".nmsship, .json or .txt files")

        description_column.separator(factor = 2)
        import_row = description_column.row(align=True)
        import_row.scale_y = 2
        import_row.operator(ImportShipFile.bl_idname, icon="IMPORT")

        description_column.separator()
        export_row = description_column.row(align=True)
        export_row.scale_y = 2
        export_row.operator(ExportShipFile.bl_idname, icon="EXPORT")



classes = (
    CHARON_PT_crossing_panel,
)
