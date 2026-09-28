from bpy.types import Panel

# Game Lighting, drawn into The Watchtower panel itself (draw_game_lighting,
# called from its draw - no sub-panel, so no collapse arrow), plus the folded
# Advanced section, The Watchtower's only sub-panel.

WATCHTOWER_PANEL = "CHARON_PT_the_watchtower_panel"


def draw_game_lighting(layout, context):
    """Say where the build is, pick one of the game's skies, done."""
    from ..lighting import data, game_lights, viewports

    settings = getattr(context.scene, "charon_lighting", None)
    if settings is None:
        layout.label(text="Lighting is not registered", icon="ERROR")
        return
    if not data.available():
        layout.label(text="resources/lighting/lighting.json is missing", icon="ERROR")
        return

    # the one on / off switch
    row = layout.row()
    row.scale_y = 1.2
    row.prop(settings, "enabled", toggle=True, icon="LIGHT_SUN",
             text="Game Lighting On" if settings.enabled else "Use Game Lighting")
    if not settings.enabled:
        return

    # the parts' game lamps
    row = layout.row(align=True)
    row.prop(settings, "game_lights", toggle=True, icon="LIGHT_POINT",
             text="Lamps On" if settings.game_lights else "Lamps Off")
    sub = row.row(align=True)
    sub.enabled = settings.game_lights
    sub.operator("object.charon_lighting_refresh_lamps", text="", icon="FILE_REFRESH")
    if settings.game_lights:
        layout.label(text="%d lamps lighting the scene" % game_lights.count(),
                     icon="BLANK1")

    # where ---
    row = layout.row(align=True)
    row.scale_y = 1.2
    row.prop(settings, "context", expand=True)
    # turning the lighting on switched every 3D view to it; a view opened or
    # changed since gets one button
    if viewports.needs_switch(getattr(context.space_data, "shading", None)):
        row = layout.row()
        row.alert = True
        row.operator("object.charon_lighting_show_in_views", icon="SHADING_RENDERED")

    # the sky ---
    box = layout.box()
    if settings.context == "PLANET":
        _draw_planet(box, settings)
    elif settings.context == "STATION":
        _draw_station(box, settings)     # only while STATION_ENABLED is on
    else:
        _draw_space(box, settings)

    # presets ---
    row = layout.row(align=True)
    row.prop(settings, "preset", text="", icon="PRESET")
    row.operator("object.charon_lighting_load_preset", text="", icon="IMPORT")
    row.operator("object.charon_lighting_save_preset", text="", icon="ADD")
    row.operator("object.charon_lighting_delete_preset", text="", icon="TRASH")


def _sky_picker(box, settings, top_prop, bottom_prop, picker_prop):
    """The list choice on the left - under it the second choice with the
    randomise button - and a small swatch of the sky on the right; click the
    swatch for the full grid."""
    split = box.split(factor=0.74)
    left = split.column(align=True)
    left.prop(settings, top_prop, text="")
    row = left.row(align=True)
    row.operator("object.charon_lighting_surprise", text="", icon="FILE_REFRESH")
    row.prop(settings, bottom_prop, text="")
    split.column().template_icon_view(settings, picker_prop, show_labels=False,
                                      scale=2.2, scale_popup=4.0)


def _sun_row(box, settings):
    row = box.row(align=True)
    row.prop(settings, "sun_heading", text="Sun", slider=True)
    row.prop(settings, "sun_height", text="Height", slider=True)


def _draw_planet(box, settings):
    _sky_picker(box, settings, "planet_list", "weather", "planet_sky")
    row = box.row(align=True)
    row.prop(settings, "time_of_day", text="Time", slider=True)
    row.prop(settings, "sun_heading", text="Sun", slider=True)


def _draw_space(box, settings):
    # the nebula shape has no slider: the randomise button picks it
    _sky_picker(box, settings, "star_filter", "space_style", "space_sky")
    _sun_row(box, settings)


def _draw_station(box, settings):
    # the outside's colours are switched off for now (rig._apply_space): a
    # dark starry sky and the game's SpaceLightColour
    box.prop(settings, "station_type", text="")
    _sun_row(box, settings)


class CHARON_PT_the_watchtower_lighting_advanced(Panel):
    """Everything the look is made of, for fine-tuning a shot."""

    bl_idname = "CHARON_PT_the_watchtower_lighting_advanced"
    bl_label = "Game Lighting: Advanced"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Charon Forge"
    bl_context = "objectmode"
    bl_parent_id = WATCHTOWER_PANEL
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "charon_lighting", None)
        return settings is not None and settings.enabled

    def draw(self, context):
        settings = context.scene.charon_lighting
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        self.group(layout, settings, ("brightness", "sunlight", "glow"))
        self.group(layout, settings, ("ambient", "sky_brightness"))
        self.group(layout, settings, ("sun_size", "sun_glow", "sun_halo"))
        if settings.context == "PLANET":
            self.group(layout, settings, ("noon_height", "night_light"))
            layout.prop(settings, "dark_night")
        else:
            self.group(layout, settings, ("nebula", "clouds", "stars"))

        view = context.scene.view_settings
        column = layout.column(align=True)
        column.prop(view, "view_transform", text="View")
        column.prop(view, "look")
        eevee = getattr(context.scene, "eevee", None)
        if eevee is not None and hasattr(eevee, "use_raytracing") \
                and context.scene.render.engine != "CYCLES":
            layout.prop(eevee, "use_raytracing", text="EEVEE Raytracing")

    @staticmethod
    def group(layout, settings, names):
        column = layout.column(align=True)
        for name in names:
            column.prop(settings, name, slider=True)


classes = (
    CHARON_PT_the_watchtower_lighting_advanced,
)
