"""Turning the panel's settings into the scene's lighting.

    enable(scene)    put the rig in, remembering what it replaces
    disable(scene)   take it out, giving everything back
    apply(scene)     settings -> the Charon Sky world, the Charon Sun and the
                     view exposure; only values change - no material, no part -
                     so it runs on every slider step with any number of parts
    apply_game_lights(scene)   the game lamp layer on or off (kept out of
                     apply: it touches every mesh)

Where the light comes from:

    PLANET     a day entry (by biome list, weather and sky), blended with the
               dusk and night entries by time of day, using the game's own
               fade thresholds (MinSunsetFade.., MinNightFade..)
    SPACE      a space sky entry (58, common and rare) - its gradient, nebula
               colours and LightColour - drawn in one of the Sky Styles
    STATION    (hidden for now, properties.STATION_ENABLED) a dark starry sky
               with no colours, lit by the game's SpaceLightColour; the rooms
               by the parts' game lamps. DERELICT swaps the sky for
               AbandonedFreighterFogColour, dim.

Every colour and the fade thresholds are the game's. The absolute strengths
(sunlight W/m2, sky light, sun disc) are first guesses, to be calibrated
against in-game screenshots; they are the Advanced sliders.
"""

import math

import bpy
import mathutils

from . import data, game_lights, sky, viewports

SUN_NAME = "Charon Sun"
RIG_COLLECTION = "Charon Lighting"
SAVED_PROP = "charon_lighting_saved"

STATION_PLACES = {"STATION", "FREIGHTER", "DERELICT", "ANOMALY"}
WEATHER_LISTS = {"NORMAL": "day", "FIRESTORM": "day_firestorm",
                 "GRAVSTORM": "day_gravstorm"}

# what each space Sky Style does to the sky's layers: x nebula, x clouds,
# x stars, star field strength, galaxy band strength, x gradient brightness.
# The dark styles are dark in display terms: sRGB lifts a linear 0.04 to a
# visible 22% grey, so their nebula runs at a few percent (measured).
STYLE_LAYERS = {
    "NEBULA": dict(nebula=1.0, clouds=1.0, stars=1.0, field=0.4, band=0.0, dark=1.0),
    "STORM": dict(nebula=1.4, clouds=2.8, stars=0.5, field=0.2, band=0.0, dark=1.3),
    "GALAXY": dict(nebula=0.1, clouds=0.15, stars=1.3, field=1.6, band=0.9, dark=0.3),
    "STARFIELD": dict(nebula=0.04, clouds=0.05, stars=2.0, field=3.0, band=0.0, dark=0.2),
    "DEEP": dict(nebula=0.012, clouds=0.0, stars=1.2, field=0.8, band=0.0, dark=0.08),
}


def place_of(settings):
    """PLANET, SPACE, or the station type."""
    return settings.station_type if settings.context == "STATION" else settings.context


# Enable / disable ---
def enable(scene):
    """Put the rig in and remember what it replaced."""
    if SAVED_PROP not in scene:
        view = scene.view_settings
        scene[SAVED_PROP] = {
            "world": scene.world.name if scene.world else "",
            "view_transform": view.view_transform,
            "look": view.look,
            "exposure": view.exposure,
            "gamma": view.gamma,
            "viewports": viewports.remember(scene),
        }
        # the sky tables hold display colours: Standard shows them as they
        # are, where Blender's default AgX washes a blue sky out to grey
        # (measured on the same render). Changeable in Advanced.
        try:
            view.view_transform = "Standard"
            view.look = "None"
        except TypeError:
            pass
    # older glow wiring gets the Glow slider's multiplier (materials skip
    # themselves once done)
    from .. import materials
    materials.prepare_materials()
    scene.world = sky.ensure_world()
    _sun(scene).hide_viewport = False
    viewports.show_game_lighting(scene)
    apply(scene)
    apply_game_lights(scene)


def disable(scene):
    """Take the rig out and give back the world, view and viewports."""
    from ..materials import emission
    sun = bpy.data.objects.get(SUN_NAME)
    if sun is not None:
        sun.hide_viewport = sun.hide_render = True
    game_lights.set_visible(scene, False)
    emission.set_lamps(True)
    emission.set_glow(scene, 1.0)

    saved = scene.get(SAVED_PROP)
    if not saved:
        # nothing remembered (a file from before, or a lost undo step): at
        # least do not leave the game sky behind
        if scene.world is not None and scene.world.name == sky.WORLD_NAME:
            scene.world = next((w for w in bpy.data.worlds
                                if w.name != sky.WORLD_NAME), None)
        return
    saved = saved.to_dict() if hasattr(saved, "to_dict") else dict(saved)
    scene.world = bpy.data.worlds.get(saved.get("world", "")) or None
    view = scene.view_settings
    for key in ("view_transform", "look", "exposure", "gamma"):
        try:
            setattr(view, key, saved[key])
        except (KeyError, TypeError, ValueError):
            pass
    viewports.restore(scene, saved.get("viewports"))
    del scene[SAVED_PROP]


def _sun(scene):
    """The Charon Sun, linked into this scene through the Charon Lighting
    collection - also when it was made in another scene."""
    coll = bpy.data.collections.get(RIG_COLLECTION) \
        or bpy.data.collections.new(RIG_COLLECTION)
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    obj = bpy.data.objects.get(SUN_NAME)
    if obj is None:
        light = bpy.data.lights.get(SUN_NAME) or bpy.data.lights.new(SUN_NAME, "SUN")
        obj = bpy.data.objects.new(SUN_NAME, light)
        obj.hide_select = True
    if obj.name not in coll.objects:
        coll.objects.link(obj)
    return obj


# The sun's path ---
def smoothstep(e0, e1, x):
    if e1 <= e0:
        return 1.0 if x >= e1 else 0.0
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def _sun_direction(elevation_deg, heading_deg):
    """Unit vector toward the sun, Blender Z up."""
    e, h = math.radians(elevation_deg), math.radians(heading_deg)
    return mathutils.Vector((math.cos(e) * math.sin(h),
                             -math.cos(e) * math.cos(h),
                             math.sin(e)))


def _planet_path(time_of_day, heading_deg, max_elevation_deg):
    """The sun's direction over the day. The game turns the sun about one
    axis (SunRotationAxis, X); here that circle is tilted so noon peaks at
    `max_elevation_deg` and then turned by the heading. 0.25 is sunrise,
    0.5 noon, 0.75 sunset."""
    a = (time_of_day - 0.25) * 2.0 * math.pi
    tilt = math.radians(90.0 - max_elevation_deg)
    v = mathutils.Vector((math.cos(a), -math.sin(a) * math.sin(tilt),
                          math.sin(a) * math.cos(tilt)))
    v.rotate(mathutils.Matrix.Rotation(math.radians(heading_deg), 3, "Z"))
    return v


def planet_state(s):
    """The blended planet sky for the settings: colours (linear) and weights."""
    g = data.sky_globals()
    list_name = s.planet_list
    try:
        day_index = int(s.planet_sky)
    except (TypeError, ValueError):
        day_index = 0
    day = data.planet_entry(WEATHER_LISTS.get(s.weather, "day"), list_name, day_index)
    dusk = data.planet_entry("dusk", list_name, 0)
    night = data.planet_entry("night", "Dark" if s.dark_night else list_name, 0)

    # 0 at noon, 1 at midnight - the axis the game's fade thresholds are on
    from_noon = abs(s.time_of_day - 0.5) * 2.0
    w_dusk = smoothstep(g.get("MinSunsetFade", 0.4), g.get("MaxSunsetFade", 0.5),
                        from_noon)
    w_night = smoothstep(g.get("MinNightFade", 0.62), g.get("MaxNightFade", 0.68),
                         from_noon)

    def colour(key):
        c = data.lerp(data.to_linear(day.get(key, (0, 0, 0))),
                      data.to_linear(dusk.get(key, (0, 0, 0))), w_dusk)
        return data.lerp(c, data.to_linear(night.get(key, (0, 0, 0))), w_night)

    return {
        "sky": colour("SkyColour"), "upper": colour("SkyUpperColour"),
        "horizon": colour("HorizonColour"), "fog": colour("FogColour"),
        "sun": colour("SunColour"), "solar": colour("SkySolarColour"),
        "light": colour("LightColour"), "w_dusk": w_dusk, "w_night": w_night,
    }


# Applying ---
def _apply_planet(world, s):
    """Returns (direction the light comes from, strength, colour)."""
    state = planet_state(s)
    toward = _planet_path(s.time_of_day, s.sun_heading, s.noon_height)
    night = state["w_night"]
    sky.set_mode(world, "planet")
    sky.set_planet_gradient(world, data.scale(state["fog"], 0.6),
                            state["horizon"], state["sky"], state["upper"])
    sky.set_sun(world, toward, state["sun"], state["solar"], s.sun_size,
                s.sun_glow * (1.0 - night), s.sun_halo * (1.0 - night))
    # below the horizon the light that is left comes from the other side
    # (the night light), dimmed by `night_light`
    light_dir = toward if toward.z >= 0.0 else -toward
    strength = s.sunlight * (1.0 - night * (1.0 - s.night_light))
    return light_dir, strength, state["light"]


def _apply_space(world, s, place):
    """Returns (direction the light comes from, strength, colour)."""
    g = data.sky_globals()
    entry = data.space_entry_by_key(s.space_sky or "c0")

    def lin(key):
        return data.to_linear(entry.get(key, (0, 0, 0)))

    toward = _sun_direction(s.sun_height, s.sun_heading)
    sky.set_mode(world, "space")
    sky.set_nebula_shape(world, s.nebula_shape)

    if place not in STATION_PLACES:
        station_light = None
        style = STYLE_LAYERS.get(s.space_style, STYLE_LAYERS["NEBULA"])
        dim = 0.15 * style["dark"]
        sky.set_space_gradient(world, data.scale(lin("BottomColour"), dim),
                               data.scale(lin("MidColour"), dim),
                               data.scale(lin("TopColour"), dim))
        sky.set_nebula(world, [lin("NebulaColour1"), lin("NebulaColour2"),
                               lin("NebulaColour3")], s.nebula * style["nebula"],
                       s.stars * style["stars"], s.clouds * style["clouds"])
        # the band is the sky's own colours: its first nebula colour lifted
        # toward the star light
        band_colour = data.lerp(lin("NebulaColour1"), lin("LightColour"), 0.5)
        sky.set_star_style(world, style["field"] * s.stars / 2.0,
                           style["band"] * s.nebula, band_colour)
    else:
        # inside a station the sky colours are switched off for now: the
        # outside is dark and starry, lit by the game's own SpaceLightColour
        station_light = data.to_linear(g.get("SpaceLightColour", (0.92, 0.85, 0.8)))
        if place == "DERELICT":
            fog = data.to_linear(g.get("AbandonedFreighterFogColour", (0.03, 0.09, 0.19)))
            sky.set_space_gradient(world, data.scale(fog, 0.5), fog, data.scale(fog, 0.7))
            sky.set_nebula(world, [fog, fog, fog], s.nebula * 0.3, s.stars, s.clouds)
            sky.set_star_style(world, 0.3 * s.stars / 2.0, 0.0, fog)
        else:
            grey = data.scale(station_light, 0.004)
            sky.set_space_gradient(world, grey, grey, grey)
            sky.set_nebula(world, [grey, grey, grey], 0.0, s.stars, 0.0)
            sky.set_star_style(world, 0.8 * s.stars / 2.0, 0.0, grey)

    light_colour = station_light or lin("LightColour")
    sky.set_sun(world, toward, light_colour,
                light_colour if station_light else lin("CloudColour"),
                s.sun_size * 0.4, s.sun_glow, s.sun_halo * 0.5, halo_power=400.0)
    return toward, s.sunlight, light_colour


def apply(scene):
    s = scene.charon_lighting
    if not s.enabled or not data.available():
        return
    from ..materials import emission

    world = scene.world
    if world is None or world.name != sky.WORLD_NAME:
        world = sky.ensure_world()
        scene.world = world

    place = place_of(s)
    if place == "PLANET":
        light_dir, strength, light_colour = _apply_planet(world, s)
    else:
        light_dir, strength, light_colour = _apply_space(world, s, place)
    sky.set_strengths(world, s.ambient, s.sky_brightness)

    sun_obj = _sun(scene)
    sun = sun_obj.data
    sun.color = light_colour
    sun.energy = max(0.0, strength)
    sun.angle = math.radians(max(0.05, s.sun_size))
    sun_obj.rotation_mode = "QUATERNION"
    sun_obj.rotation_quaternion = light_dir.to_track_quat("Z", "Y")
    hidden = strength <= 0.0
    if sun_obj.hide_render != hidden or sun_obj.hide_viewport != hidden:
        sun_obj.hide_viewport = sun_obj.hide_render = hidden

    if scene.view_settings.exposure != s.brightness:
        scene.view_settings.exposure = s.brightness

    emission.set_glow(scene, s.glow)
    game_lights.set_visible(scene, s.game_lights)
    if s.game_lights:
        game_lights.set_power(s.glow)


def apply_game_lights(scene, rebuild=False):
    """Switch the game lamp layer to match the settings."""
    from ..materials import emission
    s = scene.charon_lighting
    on = s.enabled and s.game_lights
    if on and (rebuild or game_lights.count() == 0):
        game_lights.rebuild(scene, s.glow)
    game_lights.set_visible(scene, on)
    # one or the other lights the scene, never both
    emission.set_lamps(not on)
