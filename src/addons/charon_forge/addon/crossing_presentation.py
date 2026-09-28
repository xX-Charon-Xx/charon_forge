from bpy.types import Panel

from ..utils import icon_utils
from .crossing_operators import (ExportShipClipboard, ExportShipFile,
                                 ImportShipChanges, ImportShipClipboard,
                                 ImportShipFile)


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
        description_icon_row.scale_x = 2
        description_icon_row.template_icon(
            icon_value=icon_utils.get_icon_id("crossing"),
            scale=3,
        )
        description_column = description_row.column(align=True)
        description_column.separator()
        description_column.label(text="Import/Export ships and bases as")
        description_column.label(text=".nmsship or .json files or clipboard")

        description_column.separator(factor = 2)
        description_column.label(text="File")
        file_row = description_column.row(align=True)
        file_row.scale_y = 2
        file_row.operator(ImportShipFile.bl_idname, icon="IMPORT")
        file_row.operator(ExportShipFile.bl_idname, icon="EXPORT")

        description_column.separator(factor = 2)
        description_column.label(text="Clipboard")
        clipboard_row = description_column.row(align=True)
        clipboard_row.scale_y = 2
        clipboard_row.operator(ImportShipClipboard.bl_idname, text="Import", icon="PASTEDOWN")
        clipboard_row.operator(ExportShipClipboard.bl_idname, text="Export", icon="COPYDOWN")
        obj_only_row = description_column.row(align = True)
        obj_only_row.scale_y = 1.4
        obj_only_row.label(text = "")
        obj_only_row.prop(context.scene.charon_crossing, "clipboard_objects_only")

        description_column.separator(factor = 2)
        description_column.label(text="Changes")
        changes_row = description_column.row(align=True)
        changes_row.scale_y = 2
        changes_row.operator_menu_enum(
            ImportShipChanges.bl_idname, "source", text="Import Changes", icon="FILE_REFRESH"
        )


classes = (
    CHARON_PT_crossing_panel,
)
