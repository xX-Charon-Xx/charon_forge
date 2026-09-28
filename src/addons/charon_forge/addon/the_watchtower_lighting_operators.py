import bpy

# The Game Lighting buttons in The Watchtower panel. The work is in the
# lighting package; these only call into it.


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


class WatchtowerLightingSurprise(bpy.types.Operator):
    """Pick a random game sky for this place - in space also a new style and
    nebula shape"""

    bl_idname = "object.charon_lighting_surprise"
    bl_label = "Random Sky"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ..lighting import properties
        properties.surprise(context.scene)
        return {"FINISHED"}


class WatchtowerLightingShowInViews(bpy.types.Operator):
    """Show the game lighting in the 3D views: Material Preview with the
    scene's lights and world"""

    bl_idname = "object.charon_lighting_show_in_views"
    bl_label = "Show Game Lighting Here"

    def execute(self, context):
        from ..lighting import viewports
        viewports.show_game_lighting(context.scene)
        return {"FINISHED"}


class WatchtowerLightingSavePreset(bpy.types.Operator):
    """Save the current lighting as a preset, for any scene"""

    bl_idname = "object.charon_lighting_save_preset"
    bl_label = "Save Lighting Preset"

    name: bpy.props.StringProperty(name="Name", default="My Lighting")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=260)

    def execute(self, context):
        from ..lighting import presets
        saved = presets.save(context.scene.charon_lighting, self.name)
        try:
            context.scene.charon_lighting.preset = saved
        except TypeError:
            pass
        self.report({"INFO"}, "Saved lighting preset %s" % saved)
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
        from ..lighting import presets
        presets.delete(context.scene.charon_lighting.preset)
        return {"FINISHED"}


classes = (
    WatchtowerLightingRefreshLamps,
    WatchtowerLightingSurprise,
    WatchtowerLightingShowInViews,
    WatchtowerLightingSavePreset,
    WatchtowerLightingLoadPreset,
    WatchtowerLightingDeletePreset,
)
