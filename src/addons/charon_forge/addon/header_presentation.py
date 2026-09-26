import bpy
from bpy.types import Panel

from .. import addon_preferences
from ..utils import icon_utils
from .header_operators import (Forge, SwitchWorkspace, VisitDiscord,
                               VisitGuides, VisitSupport)


# Hero Panel ---
class CHARON_PT_hero_panel(Panel):
    bl_idname = "CHARON_PT_hero_panel"
    bl_label = "Charon Forge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Charon Forge"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout
        main_box = layout.column(align = True)
        app_cover_row = main_box.column(align = True)
        app_cover_row.separator()
        app_cover_row.scale_y = 0.6
        app_cover_row.template_icon(
            icon_value=icon_utils.get_icon_id("app_cover_2"),
            scale=12,
        )

        
        
        #main_box.separator(factor = 2)
        main_col = main_box.column(align = True)
        link_row = main_col.row(align=True)
        link_row.scale_y = 1.2
        link_row.operator(
            VisitGuides.bl_idname,
            icon_value=icon_utils.get_icon_id("online"),
        )
        link_row.operator(
            VisitDiscord.bl_idname,
            icon_value=icon_utils.get_icon_id("discord"),
        )
        
        prefs = addon_preferences.get_addon_preferences()
        if prefs is not None:
            themes_row = main_col.box().row(align = True)
            themes_row.label(text = "Choose Aura :")
            themes_row.prop(prefs, "theme", text = "")
        




classes = (
    CHARON_PT_hero_panel,
)
