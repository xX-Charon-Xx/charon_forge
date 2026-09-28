"""scene.charon_lighting: every setting of the lighting rig, and its presets.

Each setting's update calls rig.apply, which only changes node values, the
sun and the view exposure - a slider can be dragged with thousands of parts in
the scene.

Picking a context is itself a preset: it sets the sliders to that context's
starting values (CONTEXT_DEFAULTS), which can then be changed freely. User
presets save every setting to ~/CharonForge/lighting_presets/<name>.json.
"""

import json
import os
import re

import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty,
                       IntProperty, PointerProperty, StringProperty)

from . import data, rig

PRESET_DIR = os.path.join(os.path.expanduser("~"), "CharonForge", "lighting_presets")

CONTEXTS = (
    ("PLANET", "Planet", "A planet's sky at any time of day: the game's day, "
     "dusk and night sky entries", "WORLD", 0),
    ("SPACE", "Space", "Open space: a system's space sky and star light",
     "OUTLINER_OB_LIGHTPROBE", 1),
    ("STATION", "Space Station", "Inside a station: space light, the rooms lit "
     "by the parts' own lamps", "MOD_LATTICE", 2),
    ("FREIGHTER", "Freighter", "A freighter base: space light, rooms lit by "
     "the parts' own lamps", "MOD_BUILD", 3),
    ("DERELICT", "Derelict Freighter", "An abandoned freighter: the game's "
     "derelict fog colour, dim", "GHOST_ENABLED", 4),
    ("ANOMALY", "Space Anomaly", "The Anomaly: space light and the interior's "
     "lamps", "LIGHT_AREA", 5),
    ("CATALOGUE", "Catalogue", "The game's HDRI studio light, like the build "
     "menu previews", "IMAGE_RGB", 6),
)

# the sliders a context starts from; strengths are first guesses until they
# are calibrated against the game's icons and screenshots
CONTEXT_DEFAULTS = {
    "PLANET": dict(sun_strength=3.0, ambient=0.8, sky_strength=1.0, exposure=0.0,
                   game_lights=False, sun_disc_size=1.0),
    "SPACE": dict(sun_strength=3.0, ambient=0.5, sky_strength=1.0, exposure=0.0,
                  game_lights=False, sun_elevation=35.0, sun_disc_size=0.4),
    "STATION": dict(sun_strength=1.5, ambient=0.3, sky_strength=1.0, exposure=0.5,
                    game_lights=True, sun_elevation=35.0, sun_disc_size=0.4),
    "FREIGHTER": dict(sun_strength=2.0, ambient=0.3, sky_strength=1.0, exposure=0.5,
                      game_lights=True, sun_elevation=35.0, sun_disc_size=0.4),
    "DERELICT": dict(sun_strength=0.3, ambient=0.6, sky_strength=1.0, exposure=1.0,
                     game_lights=True, sun_elevation=20.0, sun_disc_size=0.4),
    "ANOMALY": dict(sun_strength=1.0, ambient=0.4, sky_strength=1.0, exposure=0.5,
                    game_lights=True, sun_elevation=35.0, sun_disc_size=0.4),
    "CATALOGUE": dict(sun_strength=0.0, ambient=1.0, sky_strength=1.0, exposure=0.0,
                      game_lights=False, hdri_rotation=0.0),
}

# settings a preset file holds (not `enabled`: loading a preset never turns
# the rig on or off)
PRESET_KEYS = (
    "context", "planet_list", "weather", "day_index", "dark_night", "time_of_day",
    "sun_max_elevation", "night_light", "space_set", "space_index", "hdri",
    "hdri_rotation", "sun_strength", "sun_heading", "sun_elevation",
    "sun_disc_size", "sun_disc_strength", "sun_halo", "ambient", "sky_strength",
    "nebula_strength", "star_strength", "exposure", "game_lights",
    "game_light_power",
)

_applying = False
# Blender keeps only the strings of a dynamic enum's items alive while
# something references them
_enum_cache = {}


def _apply(self, context):
    if _applying:
        return
    rig.apply(context.scene)


def _on_enabled(self, context):
    if self.enabled:
        rig.enable(context.scene)
    else:
        rig.disable(context.scene)


def _on_context(self, context):
    global _applying
    _applying = True
    try:
        for key, value in CONTEXT_DEFAULTS.get(self.context, {}).items():
            setattr(self, key, value)
        if self.context == "CATALOGUE" and not self.hdri and data.hdri_names():
            self.hdri = "default.hdr" if "default.hdr" in data.hdri_names() \
                else data.hdri_names()[0]
    finally:
        _applying = False
    rig.apply(context.scene)
    rig.apply_game_lights(context.scene)


def _on_game_lights(self, context):
    if _applying:
        return
    rig.apply_game_lights(context.scene)


def _on_game_light_power(self, context):
    from . import game_lights
    game_lights.set_power(self.game_light_power)


def _planet_list_items(self, context):
    items = [(n, n if n != "Generic" else "All Biomes",
              "The %s day sky list" % n) for n in data.planet_list_names()]
    _enum_cache["planet_list"] = items
    return items


def _hdri_items(self, context):
    items = [(n, n.rsplit(".", 1)[0].replace("_", " ").title(), n)
             for n in data.hdri_names()] or [("", "None", "No HDRIs found")]
    _enum_cache["hdri"] = items
    return items


def _preset_items(self, context):
    names = []
    if os.path.isdir(PRESET_DIR):
        names = sorted(f[:-5] for f in os.listdir(PRESET_DIR) if f.endswith(".json"))
    items = [(n, n, "Lighting preset %s" % n) for n in names] \
        or [("", "No presets saved", "")]
    _enum_cache["presets"] = items
    return items


class CharonLightingSettings(bpy.types.PropertyGroup):
    enabled: BoolProperty(
        name="Game Lighting",
        description="Light the scene with the game's sky, sun and lamps. "
                    "Turning it off gives back the world and view it replaced",
        default=False, update=_on_enabled)
    context: EnumProperty(
        name="Context", items=CONTEXTS, default="PLANET", update=_on_context)

    # planet ---
    planet_list: EnumProperty(
        name="Biome Skies", items=_planet_list_items, update=_apply,
        description="Which day sky list: the generic one every biome uses, or "
                    "a biome with its own")
    weather: EnumProperty(
        name="Weather",
        items=(("NORMAL", "Clear", "The ordinary day skies"),
               ("FIRESTORM", "Firestorm", "The firestorm day skies"),
               ("GRAVSTORM", "Gravity Storm", "The gravity storm day skies")),
        default="NORMAL", update=_apply)
    day_index: IntProperty(
        name="Day Sky", min=0, default=0, update=_apply,
        description="Which entry of the day sky list - a planet keeps one "
                    "for good, picked from its seed")
    dark_night: BoolProperty(
        name="Dark Night", default=False, update=_apply,
        description="The darker night sky the game uses on some planets")
    time_of_day: FloatProperty(
        name="Time of Day", min=0.0, max=1.0, default=0.45, update=_apply,
        subtype="FACTOR",
        description="0.25 sunrise, 0.5 noon, 0.75 sunset, 0 / 1 midnight. The "
                    "day, dusk and night skies blend at the game's thresholds")
    sun_max_elevation: FloatProperty(
        name="Noon Height", min=5.0, max=90.0, default=55.0, update=_apply,
        subtype="NONE", unit="NONE",
        description="How high the sun climbs at noon, in degrees (the game "
                    "clamps its sun at 55)")
    night_light: FloatProperty(
        name="Night Light", min=0.0, max=1.0, default=0.25, update=_apply,
        subtype="FACTOR", description="How much of the sun's strength is left at night")

    # space ---
    space_set: EnumProperty(
        name="Space Skies",
        items=(("common", "Common", "The 10 common space skies"),
               ("rare", "Rare", "The 48 rare space skies")),
        default="common", update=_apply)
    space_index: IntProperty(
        name="Space Sky", min=0, default=0, update=_apply,
        description="Which space sky entry - a system keeps one, picked from its seed")

    # catalogue ---
    hdri: EnumProperty(name="HDRI", items=_hdri_items, update=_apply)
    hdri_rotation: FloatProperty(
        name="Rotation", min=-180.0, max=180.0, default=0.0, update=_apply)

    # sun and sky ---
    sun_strength: FloatProperty(
        name="Sun Strength", min=0.0, soft_max=20.0, default=3.0, update=_apply,
        description="The sun light's strength in W/m²")
    sun_heading: FloatProperty(
        name="Sun Heading", min=-180.0, max=180.0, default=30.0, update=_apply,
        description="Which way the sun's path runs, in degrees")
    sun_elevation: FloatProperty(
        name="Sun Height", min=-90.0, max=90.0, default=35.0, update=_apply,
        description="The sun's height above the horizon, in degrees")
    sun_disc_size: FloatProperty(
        name="Sun Size", min=0.05, max=10.0, default=1.0, update=_apply,
        description="The sun disc's radius in degrees; also softens its shadows")
    sun_disc_strength: FloatProperty(
        name="Sun Glow", min=0.0, soft_max=100.0, default=20.0, update=_apply,
        description="How bright the sun disc is in the sky")
    sun_halo: FloatProperty(
        name="Halo", min=0.0, soft_max=2.0, default=0.3, update=_apply,
        description="The glow around the sun")
    ambient: FloatProperty(
        name="Ambient", min=0.0, soft_max=4.0, default=0.8, update=_apply,
        description="How strongly the sky lights the scene")
    sky_strength: FloatProperty(
        name="Sky Brightness", min=0.0, soft_max=4.0, default=1.0, update=_apply,
        description="How bright the sky looks to the camera (does not change "
                    "how it lights the scene)")
    nebula_strength: FloatProperty(
        name="Nebula", min=0.0, soft_max=4.0, default=0.6, update=_apply)
    star_strength: FloatProperty(
        name="Stars", min=0.0, soft_max=10.0, default=2.0, update=_apply)
    exposure: FloatProperty(
        name="Exposure", soft_min=-5.0, soft_max=5.0, default=0.0, update=_apply,
        description="The view's exposure in stops")

    # the parts' own lamps ---
    game_lights: BoolProperty(
        name="Game Lamps", default=False, update=_on_game_lights,
        description="Give every part its game lamps as real lights, in the "
                    "'Charon Game Lights' collection. They light the scene in "
                    "EEVEE and Cycles alike; the glow boost is switched off "
                    "meanwhile so nothing is counted twice")
    game_light_power: FloatProperty(
        name="Lamp Power", min=0.0, soft_max=10.0, default=1.0,
        update=_on_game_light_power,
        description="Scales every game lamp's power")

    # presets ---
    preset: EnumProperty(name="Preset", items=_preset_items)


# Presets ---
def preset_path(name):
    safe = re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "Preset"
    return os.path.join(PRESET_DIR, safe + ".json")


def save_preset(settings, name):
    os.makedirs(PRESET_DIR, exist_ok=True)
    values = {key: getattr(settings, key) for key in PRESET_KEYS}
    path = preset_path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(values, f, indent=1)
    return path


def load_preset(scene, name):
    global _applying
    with open(preset_path(name), encoding="utf-8") as f:
        values = json.load(f)
    settings = scene.charon_lighting
    _applying = True
    try:
        for key in PRESET_KEYS:
            if key in values:
                try:
                    setattr(settings, key, values[key])
                except (TypeError, ValueError):
                    pass
    finally:
        _applying = False
    rig.apply(scene)
    rig.apply_game_lights(scene)


def delete_preset(name):
    path = preset_path(name)
    if os.path.exists(path):
        os.remove(path)


def register():
    bpy.utils.register_class(CharonLightingSettings)
    bpy.types.Scene.charon_lighting = PointerProperty(type=CharonLightingSettings)


def unregister():
    if hasattr(bpy.types.Scene, "charon_lighting"):
        del bpy.types.Scene.charon_lighting
    bpy.utils.unregister_class(CharonLightingSettings)
