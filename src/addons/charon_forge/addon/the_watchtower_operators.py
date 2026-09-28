import os

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

        labels_box = settings.box()
        labels_box.prop(prefs, "watchtower_show_primary_labels")

    @staticmethod
    def draw_setting(layout, prefs, label, show_prop, position_prop):
        box = layout.box()
        column = box.column(align=True)
        column.prop(prefs, show_prop, text=label)
        position_row = column.row(align=True)
        position_row.enabled = getattr(prefs, show_prop)
        position_row.label(text="Position :", icon="BLANK1")
        position_row.prop(prefs, position_prop, expand=True)


# Game lighting ---
class WatchtowerLightingRefreshLamps(bpy.types.Operator):
    """Make the game lamps again for every part in the scene - after parts
    were added or removed"""

    bl_idname = "object.charon_lighting_refresh_lamps"
    bl_label = "Refresh Lamps"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ..lighting import game_lights, rig
        rig.apply_game_lights(context.scene, rebuild=True)
        self.report({"INFO"}, "%d game lamps" % game_lights.count())
        return {"FINISHED"}


class WatchtowerLightingSavePreset(bpy.types.Operator):
    """Save the current lighting as a preset, for any scene"""

    bl_idname = "object.charon_lighting_save_preset"
    bl_label = "Save Lighting Preset"

    name: bpy.props.StringProperty(name="Name", default="My Lighting")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=260)

    def execute(self, context):
        from ..lighting import properties
        path = properties.save_preset(context.scene.charon_lighting, self.name)
        try:
            context.scene.charon_lighting.preset = os.path.basename(path)[:-5]
        except TypeError:
            pass
        self.report({"INFO"}, "Saved lighting preset %s" % self.name)
        return {"FINISHED"}


class WatchtowerLightingLoadPreset(bpy.types.Operator):
    """Apply the chosen lighting preset"""

    bl_idname = "object.charon_lighting_load_preset"
    bl_label = "Load"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.charon_lighting.preset)

    def execute(self, context):
        from ..lighting import properties
        try:
            properties.load_preset(context.scene, context.scene.charon_lighting.preset)
        except (OSError, ValueError) as exc:
            self.report({"ERROR"}, "Could not load the preset: %s" % exc)
            return {"CANCELLED"}
        return {"FINISHED"}


class WatchtowerLightingDeletePreset(bpy.types.Operator):
    """Delete the chosen lighting preset from disk"""

    bl_idname = "object.charon_lighting_delete_preset"
    bl_label = "Delete Lighting Preset"

    @classmethod
    def poll(cls, context):
        return bool(context.scene.charon_lighting.preset)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        from ..lighting import properties
        properties.delete_preset(context.scene.charon_lighting.preset)
        return {"FINISHED"}


classes = (
    WatchtowerOverlayOptions,
    WatchtowerLightingRefreshLamps,
    WatchtowerLightingSavePreset,
    WatchtowerLightingLoadPreset,
    WatchtowerLightingDeletePreset,
)
