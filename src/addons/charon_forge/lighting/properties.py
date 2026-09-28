"""scene.charon_lighting: every setting of the lighting rig.

Laid out for picking a look, not for tuning one:

    where      Planet / Space (/ Station: space station, freighter, derelict
               freighter or the Space Anomaly - hidden for now, see
               STATION_ENABLED)
    the sky    a picker of the game's own skies with preview swatches - the
               planet day skies (by biome list and weather) or the 58 space
               skies (by star colour, in a Sky Style) - plus time of day or
               the sun's direction
    lamps      the parts' game lamps, once the lighting is on
    advanced   Brightness, Sunlight, Glow and the rest, folded away

Each setting's update calls rig.apply, which only changes node values, the
sun and the view - a slider can be dragged with thousands of parts in the
scene. Picking where (and the station type) sets the sliders to that place's
starting values (PLACE_DEFAULTS), so a new scene looks right before anything
is touched. Presets are in presets.py.
"""

import contextlib
import random

import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty,
                       IntProperty, PointerProperty)

from . import data, presets, previews, rig

CONTEXTS = (
    ("PLANET", "Planet", "On a planet: the game's day, dusk and night skies",
     "WORLD", 0),
    ("SPACE", "Space", "In open space: a system's space sky and star light",
     "SHADING_RENDERED", 1),
)
# Station is switched off for now (the user, 2026-09-28): everything for it
# stays in place - flip this to bring the Station button back
STATION_ENABLED = False
if STATION_ENABLED:
    CONTEXTS = CONTEXTS + (
        ("STATION", "Station", "Inside: a space station, freighter, derelict or "
         "the Anomaly. Turn Lamps on to light the rooms with the parts' own lamps",
         "HOME", 2),
    )
STATION_TYPES = (
    ("STATION", "Space Station", "A space station interior", "MOD_LATTICE", 0),
    ("FREIGHTER", "Freighter", "A freighter base", "MOD_BUILD", 1),
    ("DERELICT", "Derelict Freighter", "An abandoned freighter: the game's "
     "derelict fog colour, dim", "GHOST_ENABLED", 2),
    ("ANOMALY", "Space Anomaly", "The Space Anomaly", "LIGHT_AREA", 3),
)
STAR_COLOURS = ("Yellow", "Red", "Green", "Blue", "Purple")
SPACE_STYLES = (
    ("NEBULA", "Nebula", "The game's nebula dome with clouds and wisps",
     "OUTLINER_DATA_VOLUME", 0),
    ("STORM", "Nebula Storm", "Dense, bright nebula clouds filling the sky",
     "FORCE_TURBULENCE", 1),
    ("GALAXY", "Galaxy", "A band of dust and crowded stars across the sky, "
     "faint nebula", "FORCE_VORTEX", 2),
    ("STARFIELD", "Starfield", "Stars everywhere, the nebula faded back",
     "SOLO_ON", 3),
    ("DEEP", "Deep Space", "Dark and empty: sparse stars, a trace of nebula",
     "RADIOBUT_OFF", 4),
)
WEATHERS = (("NORMAL", "Clear", "The ordinary day skies"),
            ("FIRESTORM", "Firestorm", "The firestorm day skies"),
            ("GRAVSTORM", "Gravity Storm", "The gravity storm day skies"))
LIST_NAMES = {"Generic": "All Biomes", "GasGiant": "Gas Giant"}

# what Space starts with (the user's pick, 2026-09-29): rare sky 38 - key
# 'r37' - drawn as a Starfield
DEFAULT_SPACE_SKY = "r37"
DEFAULT_SPACE_STYLE = "STARFIELD"


def _default_space_sky_number():
    """A dynamic enum takes its default as the item's number - here its place
    in data.space_sky_keys(), the numbers _space_sky_items gives."""
    keys = [key for key, _, _, _ in data.space_sky_keys()]
    return keys.index(DEFAULT_SPACE_SKY) if DEFAULT_SPACE_SKY in keys else 0

# the starting values for each place; strengths are first guesses until they
# are calibrated against in-game screenshots. They never touch the lamps.
#
# The lamps are the user's alone (their call, 2026-09-29): only clicking Lamps
# turns them on. Turning the lighting on always starts them off, switching
# place leaves them as they are, and presets do not store them.
PLACE_DEFAULTS = {
    "PLANET": dict(sunlight=3.0, ambient=0.8, brightness=0.0),
    "SPACE": dict(sunlight=3.0, ambient=0.5, brightness=0.0),
    "STATION": dict(sunlight=1.5, ambient=0.3, brightness=0.5),
    "FREIGHTER": dict(sunlight=2.0, ambient=0.3, brightness=0.5),
    "DERELICT": dict(sunlight=0.3, ambient=0.6, brightness=1.0),
    "ANOMALY": dict(sunlight=1.0, ambient=0.4, brightness=0.5),
}

# Blender keeps only the strings of a dynamic enum's items alive while
# something references them
_enum_cache = {}
_batching = False


@contextlib.contextmanager
def batch(scene):
    """Set many settings at once: their updates wait, and the rig is applied
    once at the end."""
    global _batching
    outer = _batching
    _batching = True
    try:
        yield scene.charon_lighting
    finally:
        _batching = outer
    if not outer:
        rig.apply(scene)
        rig.apply_game_lights(scene)


# Updates ---
# Always the scene that owns the settings (self.id_data), never
# context.scene: that is the window's scene, which is another one whenever
# the settings of a scene not on screen are changed (measured: turning a
# second scene's lighting on ran the first scene's).
def _apply(self, context):
    if not _batching:
        rig.apply(self.id_data)


def _on_enabled(self, context):
    global _batching
    if self.enabled:
        # the lamps always start off: only the Lamps button turns them on
        _batching = True
        try:
            self.game_lights = False
        finally:
            _batching = False
        rig.enable(self.id_data)
    else:
        rig.disable(self.id_data)


def _on_place(self, context):
    if _batching:
        return
    with batch(self.id_data) as s:
        for key, value in PLACE_DEFAULTS.get(rig.place_of(s), {}).items():
            setattr(s, key, value)


def _on_sky_list(self, context):
    """A new biome list or weather: keep the sky number if the new list has
    it, otherwise its first sky."""
    if _batching:
        return
    with batch(self.id_data) as s:
        # the stored number: the enum itself reads '' once the number is
        # past the end of the new list
        if s.get("planet_sky", 0) >= planet_sky_count(s):
            s.planet_sky = "0"


def _on_star_filter(self, context):
    if _batching:
        return
    with batch(self.id_data) as s:
        keys = space_keys(s.star_filter)
        if keys and s.space_sky not in keys:
            s.space_sky = keys[0]


def _on_game_lights(self, context):
    if not _batching:
        rig.apply_game_lights(self.id_data)


# Sky lists, for the pickers and the panel ---
def day_kind(settings):
    return rig.WEATHER_LISTS.get(settings.weather, "day")


def planet_sky_count(settings):
    lists = data.planet_lists(day_kind(settings))
    return len(lists.get(settings.planet_list) or lists.get("Generic") or [])


def planet_sky_index(settings):
    try:
        return int(settings.planet_sky)
    except (TypeError, ValueError):
        return 0


def space_keys(star_filter):
    return [key for key, _, _, star in data.space_sky_keys()
            if star_filter == "ALL" or star == star_filter]


def _planet_list_items(self, context):
    items = [(n, LIST_NAMES.get(n, n), "The %s day skies" % LIST_NAMES.get(n, n))
             for n in data.planet_list_names()]
    _enum_cache["planet_list"] = items
    return items


def _planet_sky_items(self, context):
    kind = day_kind(self)
    lists = data.planet_lists(kind)
    list_name = self.planet_list if self.planet_list in lists else "Generic"
    items = [(str(i), "Sky %d" % (i + 1), "Day sky %d" % (i + 1),
              previews.planet_icon(kind, list_name, i), i)
             for i in range(len(lists.get(list_name) or []))]
    _enum_cache["planet_sky"] = items or [("0", "Sky 1", "", 0, 0)]
    return _enum_cache["planet_sky"]


def _space_sky_items(self, context):
    items = []
    for number, (key, kind, i, star) in enumerate(data.space_sky_keys()):
        if self.star_filter != "ALL" and star != self.star_filter:
            continue
        label = "%s %s %d" % (star, "Rare" if kind == "rare" else "Sky", i + 1)
        items.append((key, label, "%s star, %s space sky %d" % (star, kind, i + 1),
                      previews.space_icon(key), number))
    _enum_cache["space_sky"] = items or [("c0", "Sky 1", "", 0, 0)]
    return _enum_cache["space_sky"]


def _preset_items(self, context):
    items = [(n, n, "Lighting preset %s" % n) for n in presets.names()] \
        or [("", "No presets saved", "")]
    _enum_cache["presets"] = items
    return items


class CharonLightingSettings(bpy.types.PropertyGroup):
    enabled: BoolProperty(
        name="Game Lighting",
        description="Light the scene with the game's sky, sun and lamps, and "
                    "show it in the 3D views. Turning it off gives back the "
                    "world, view and viewport shading it replaced",
        default=False, update=_on_enabled)
    context: EnumProperty(
        name="Where", items=CONTEXTS, default="PLANET", update=_on_place)
    station_type: EnumProperty(
        name="Inside", items=STATION_TYPES, default="FREIGHTER", update=_on_place)

    # planet ---
    planet_list: EnumProperty(
        name="Biome", items=_planet_list_items, update=_on_sky_list,
        description="The day skies every planet can have, or those of a "
                    "biome with its own")
    weather: EnumProperty(
        name="Weather", items=WEATHERS, default="NORMAL", update=_on_sky_list)
    planet_sky: EnumProperty(
        name="Sky", items=_planet_sky_items, update=_apply,
        description="The planet's day sky - a planet keeps one for good")
    dark_night: BoolProperty(
        name="Dark Night", default=False, update=_apply,
        description="The darker night sky some planets have")
    time_of_day: FloatProperty(
        name="Time of Day", min=0.0, max=1.0, default=0.45, update=_apply,
        subtype="FACTOR",
        description="0.25 sunrise, 0.5 noon, 0.75 sunset, 0 / 1 midnight. The "
                    "day, dusk and night skies blend at the game's thresholds")

    # space ---
    star_filter: EnumProperty(
        name="Star",
        items=[("ALL", "All Stars", "Every space sky")]
        + [(c, c, "The space skies of %s star systems" % c.lower()) for c in STAR_COLOURS],
        default="ALL", update=_on_star_filter)
    space_sky: EnumProperty(
        name="Space Sky", items=_space_sky_items, update=_apply,
        default=_default_space_sky_number(),
        description="The system's space sky - its colours and star light")
    space_style: EnumProperty(
        name="Sky Style", items=SPACE_STYLES, default=DEFAULT_SPACE_STYLE,
        update=_apply,
        description="What fills the space sky - the colours stay the sky's own")
    nebula_shape: IntProperty(
        name="Nebula Shape", min=0, soft_max=99, default=0, update=_apply,
        description="Reshapes the nebula and stars (set by the randomise "
                    "button): 0 is the game's dome as it is")

    # the sun ---
    sun_heading: FloatProperty(
        name="Sun Direction", min=-180.0, max=180.0, default=30.0, update=_apply,
        description="Which way the sunlight comes from, in degrees")
    sun_height: FloatProperty(
        name="Sun Height", min=-90.0, max=90.0, default=35.0, update=_apply,
        description="The sun's height above the horizon, in degrees")

    # the lamps ---
    game_lights: BoolProperty(
        name="Lamps", default=False, update=_on_game_lights,
        description="Give every part its game lamps as real lights (in the "
                    "'Charon Game Lights' collection), so they light the scene "
                    "in EEVEE and Cycles alike")

    # advanced ---
    brightness: FloatProperty(
        name="Brightness", soft_min=-4.0, soft_max=4.0, default=0.0, update=_apply,
        description="The camera's exposure, in stops")
    sunlight: FloatProperty(
        name="Sunlight", min=0.0, soft_max=15.0, default=3.0, update=_apply,
        description="How strong the sun (or star) light is")
    glow: FloatProperty(
        name="Glow", min=0.0, soft_max=20.0, default=1.0, update=_apply,
        description="Multiplies every glowing surface - lights, screens, "
                    "light strips - and the light the game lamps throw. "
                    "1 is the game's own")
    ambient: FloatProperty(
        name="Sky Light", min=0.0, soft_max=4.0, default=0.8, update=_apply,
        description="How strongly the sky lights the scene")
    sky_brightness: FloatProperty(
        name="Sky Brightness", min=0.0, soft_max=4.0, default=1.0, update=_apply,
        description="How bright the sky looks to the camera (not how it lights)")
    sun_size: FloatProperty(
        name="Sun Size", min=0.05, max=10.0, default=1.0, update=_apply,
        description="The sun disc's radius in degrees; also softens shadows")
    sun_glow: FloatProperty(
        name="Sun Disc", min=0.0, soft_max=100.0, default=20.0, update=_apply,
        description="How bright the sun disc is in the sky")
    sun_halo: FloatProperty(
        name="Sun Halo", min=0.0, soft_max=2.0, default=0.3, update=_apply)
    nebula: FloatProperty(
        name="Nebula", min=0.0, soft_max=3.0, default=1.0, update=_apply,
        description="How bright the nebula is")
    clouds: FloatProperty(
        name="Nebula Clouds", min=0.0, soft_max=2.0, default=0.35, update=_apply,
        description="The cloud and wisp layers the nebula shape adds")
    stars: FloatProperty(
        name="Stars", min=0.0, soft_max=10.0, default=2.0, update=_apply)
    night_light: FloatProperty(
        name="Night Light", min=0.0, max=1.0, default=0.25, update=_apply,
        subtype="FACTOR", description="How much sunlight is left at night")
    noon_height: FloatProperty(
        name="Noon Height", min=5.0, max=90.0, default=55.0, update=_apply,
        description="How high the sun climbs at noon, in degrees (the game "
                    "clamps its sun at 55)")

    # presets ---
    preset: EnumProperty(name="Preset", items=_preset_items)


# Quick actions ---
def surprise(scene):
    """A random sky for where the scene is (in space: colours, style and
    shape)."""
    with batch(scene) as s:
        s.sun_heading = random.uniform(-180.0, 180.0)
        if s.context == "PLANET":
            s.planet_sky = str(random.randrange(max(1, planet_sky_count(s))))
            s.time_of_day = random.choice((0.3, 0.4, 0.5, 0.6, 0.7))
        else:
            s.space_sky = random.choice(space_keys(s.star_filter) or ["c0"])
            s.space_style = random.choice([style[0] for style in SPACE_STYLES])
            s.nebula_shape = random.randrange(1, 100)


def load_preset(scene, name):
    with batch(scene) as s:
        for key, value in presets.read(name):
            try:
                setattr(s, key, value)
            except (TypeError, ValueError):
                pass        # a value this version no longer has


def register():
    bpy.utils.register_class(CharonLightingSettings)
    bpy.types.Scene.charon_lighting = PointerProperty(type=CharonLightingSettings)


def unregister():
    if hasattr(bpy.types.Scene, "charon_lighting"):
        del bpy.types.Scene.charon_lighting
    bpy.utils.unregister_class(CharonLightingSettings)
