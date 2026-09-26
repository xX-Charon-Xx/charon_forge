from bpy.types import Panel

from ..addon_preferences import get_addon_preferences
from ..utils import icon_utils
from .the_watchtower_operators import WatchtowerOverlayOptions

# The Watchtower Panel ---
class CHARON_PT_the_watchtower_panel(Panel):
    bl_idname = "CHARON_PT_the_watchtower_panel"
    bl_label = "The Watchtower"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Charon Forge"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout
        prefs = get_addon_preferences()

        # laid out like the crossing panel: the icon on the left, the
        # description and buttons in a column beside it
        description_row = layout.row(align = True)
        description_row.scale_y = 0.6
        description_icon_row = description_row.row(align = True)
        description_icon_row.scale_x = 1.1
        description_icon_row.template_icon(
            icon_value=icon_utils.get_icon_id("the_watchtower"),
            scale=3,
        )
        description_column = description_row.column(align=True)
        description_column.separator()
        description_column.label(text="Part count and active part")
        description_column.label(text="shown over the viewport")

        if prefs is None:
            layout.label(text="Addon preferences are not available", icon="ERROR")
            return

        shown = prefs.watchtower_show_overlay
        description_column.separator(factor = 2)
        button_row = description_column.row(align=True)
        button_row.scale_y = 2
        button_row.operator(WatchtowerOverlayOptions.bl_idname, icon="OVERLAY")
        # the eye beside it shows or hides the whole overlay in one click
        button_row.prop(
            prefs, "watchtower_show_overlay",
            text="",
            icon="HIDE_OFF" if shown else "HIDE_ON",
            toggle=True,
        )

        # the floating labels over the primary cockpit and landing bay
        description_column.separator()
        labels_row = description_column.row()
        labels_row.scale_y = 1.4
        labels_row.active = shown
        labels_row.prop(prefs, "watchtower_show_primary_labels")


classes = (
    CHARON_PT_the_watchtower_panel,
)
