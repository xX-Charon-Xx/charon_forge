import bpy

from ..addon_preferences import get_addon_preferences


class WatchtowerOverlayOptions(bpy.types.Operator):
    """Choose what the Watchtower shows over the viewport, and where"""

    bl_idname = "object.charon_watchtower_overlay_options"
    bl_label = "Overlay Options"

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=260)

    def execute(self, context):
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.label(text="Overlay Options", icon="OVERLAY")
        layout.separator()

        prefs = get_addon_preferences()
        if prefs is None:
            layout.label(text="Addon preferences are not available", icon="ERROR")
            return

        shown = prefs.watchtower_show_overlay
        toggle_row = layout.row()
        toggle_row.scale_y = 1.4
        toggle_row.prop(
            prefs, "watchtower_show_overlay",
            text="Hide Overlay" if shown else "Show Overlay",
            icon="HIDE_OFF" if shown else "HIDE_ON",
            toggle=True,
        )
        layout.separator()

        # the settings stay editable while the overlay is hidden, greyed out
        settings = layout.column()
        settings.active = shown
        self.draw_setting(
            settings, prefs, "Part Count",
            "watchtower_show_part_count", "watchtower_part_count_position",
        )
        self.draw_setting(
            settings, prefs, "Active Part",
            "watchtower_show_active_object", "watchtower_active_object_position",
        )

    @staticmethod
    def draw_setting(layout, prefs, label, show_prop, position_prop):
        box = layout.box()
        column = box.column(align=True)
        column.prop(prefs, show_prop, text=label)
        position_row = column.row(align=True)
        position_row.enabled = getattr(prefs, show_prop)
        position_row.label(text="Position :", icon="BLANK1")
        position_row.prop(prefs, position_prop, expand=True)


classes = (
    WatchtowerOverlayOptions,
)
