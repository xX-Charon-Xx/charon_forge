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


# Game Lighting ---
class CHARON_PT_the_watchtower_lighting_panel(Panel):
    """The game's lighting for the scene: pick where the build is (planet,
    space, station, freighter, derelict, Anomaly, catalogue), then the sky it
    has, then fine-tune. Everything here changes node values and one sun, so
    it stays instant however many parts there are."""

    bl_idname = "CHARON_PT_the_watchtower_lighting_panel"
    bl_label = "Game Lighting"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Charon Forge"
    bl_context = "objectmode"
    bl_parent_id = CHARON_PT_the_watchtower_panel.bl_idname

    def draw_header(self, context):
        settings = getattr(context.scene, "charon_lighting", None)
        if settings is not None:
            self.layout.prop(settings, "enabled", text="")

    def draw(self, context):
        from ..lighting import data, game_lights

        layout = self.layout
        settings = getattr(context.scene, "charon_lighting", None)
        if settings is None:
            layout.label(text="Lighting is not registered", icon="ERROR")
            return
        if not data.available():
            layout.label(text="resources/lighting/lighting.json is missing",
                         icon="ERROR")
            return

        if not settings.enabled:
            row = layout.row()
            row.scale_y = 1.6
            row.prop(settings, "enabled", text="Use Game Lighting",
                     icon="LIGHT_SUN", toggle=True)
            return

        body = layout.column()
        body.use_property_split = True
        body.use_property_decorate = False

        row = body.row()
        row.scale_y = 1.3
        row.prop(settings, "context", text="Where")

        # Material Preview lights with Blender's own studio HDRI unless told
        # to use the scene's - the rig is invisible there otherwise
        space = context.space_data
        shading = getattr(space, "shading", None)
        if shading is not None and shading.type == "MATERIAL" and \
                not (shading.use_scene_world and shading.use_scene_lights):
            row = body.row(align=True)
            row.alert = True
            row.prop(shading, "use_scene_lights", text="Scene Lights", toggle=True)
            row.prop(shading, "use_scene_world", text="Scene World", toggle=True)
        elif shading is not None and shading.type in ("SOLID", "WIREFRAME"):
            body.label(text="Switch the viewport to Material Preview or "
                            "Rendered to see it", icon="SHADING_RENDERED")

        # where the light comes from, by context ---
        box = body.box()
        if settings.context == "PLANET":
            self.draw_planet(box, settings, data)
        elif settings.context == "CATALOGUE":
            box.prop(settings, "hdri")
            box.prop(settings, "hdri_rotation")
        else:
            self.draw_space(box, settings, data)

        # sun and sky ---
        box = body.box()
        box.label(text="Sun and Sky", icon="LIGHT_SUN")
        column = box.column(align=True)
        column.prop(settings, "sun_strength")
        column.prop(settings, "sun_heading")
        if settings.context != "PLANET":
            column.prop(settings, "sun_elevation")
        column = box.column(align=True)
        column.prop(settings, "sun_disc_size")
        column.prop(settings, "sun_disc_strength")
        column.prop(settings, "sun_halo")
        column = box.column(align=True)
        column.prop(settings, "ambient")
        column.prop(settings, "sky_strength")
        if settings.context not in ("PLANET", "CATALOGUE"):
            column.prop(settings, "nebula_strength")
            column.prop(settings, "star_strength")

        # camera ---
        box = body.box()
        box.label(text="Camera", icon="CAMERA_DATA")
        box.prop(settings, "exposure")
        view = context.scene.view_settings
        box.prop(view, "view_transform", text="View")
        box.prop(view, "look")
        eevee = getattr(context.scene, "eevee", None)
        if eevee is not None and hasattr(eevee, "use_raytracing") \
                and context.scene.render.engine != "CYCLES":
            box.prop(eevee, "use_raytracing", text="EEVEE Raytracing")

        # the parts' own lamps ---
        box = body.box()
        header = box.row()
        header.label(text="Game Lamps", icon="LIGHT_POINT")
        header.prop(settings, "game_lights", text="")
        column = box.column()
        column.active = settings.game_lights
        column.prop(settings, "game_light_power")
        row = column.row()
        row.label(text="%d lamps" % game_lights.count())
        row.operator("object.charon_lighting_refresh_lamps", icon="FILE_REFRESH")

        # presets ---
        box = body.box()
        box.label(text="My Presets", icon="PRESET")
        row = box.row(align=True)
        row.prop(settings, "preset", text="")
        row.operator("object.charon_lighting_load_preset", text="", icon="IMPORT")
        row.operator("object.charon_lighting_save_preset", text="", icon="ADD")
        row.operator("object.charon_lighting_delete_preset", text="", icon="TRASH")

        note = layout.column()
        note.scale_y = 0.7
        note.label(text="Colours are the game's. Strengths are", icon="INFO")
        note.label(text="not yet calibrated to the game.", icon="BLANK1")

    @staticmethod
    def draw_planet(box, settings, data):
        box.prop(settings, "planet_list")
        box.prop(settings, "weather")
        kind = {"NORMAL": "day", "FIRESTORM": "day_firestorm",
                "GRAVSTORM": "day_gravstorm"}[settings.weather]
        lists = data.planet_lists(kind)
        count = len(lists.get(settings.planet_list) or lists.get("Generic") or [])
        row = box.row()
        row.prop(settings, "day_index")
        if count:
            row.label(text="%d of %d" % (settings.day_index % count + 1, count))
        box.prop(settings, "dark_night")
        box.prop(settings, "time_of_day", slider=True)
        column = box.column(align=True)
        column.prop(settings, "sun_max_elevation")
        column.prop(settings, "night_light", slider=True)

    @staticmethod
    def draw_space(box, settings, data):
        box.prop(settings, "space_set")
        entries = data.space_entries(settings.space_set)
        row = box.row()
        row.prop(settings, "space_index")
        if entries:
            entry = entries[settings.space_index % len(entries)]
            row.label(text="%d of %d · %s star" % (
                settings.space_index % len(entries) + 1, len(entries),
                entry.get("GalaxyStarType", "?")))


classes = (
    CHARON_PT_the_watchtower_panel,
    CHARON_PT_the_watchtower_lighting_panel,
)
