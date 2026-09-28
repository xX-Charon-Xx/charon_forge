"""Turning the panel's settings into the scene's lighting.

`apply(scene)` is the one entry point: it reads scene.charon_lighting and
writes the Charon Sky world, the Charon Sun light and the view exposure. It
only changes values - no material and no part is touched - so it is cheap
enough to run on every slider move, with any number of parts.

Contexts and where their light comes from:

    PLANET     a day entry (by biome list, weather and index), blended with
               the dusk and night entries by time of day, using the game's
               own fade thresholds (MinSunsetFade.., MinNightFade..)
    SPACE      a space sky entry (common or rare) - its gradient, nebula
               colours and LightColour
    STATION,   the same space sky; the rooms are lit by the parts' game
    FREIGHTER, lamps (game_lights.py), so the sun and ambient are lower
    ANOMALY
    DERELICT   an abandoned freighter: the space sky swapped for
               AbandonedFreighterFogColour, dim
    CATALOGUE  one of the game's HDRIs, no sun - the studio look

What is read from the game and what is not yet: every colour, the fade
thresholds and the tonemap exposure are the game's. The absolute strengths
(sun W/m2, ambient, disc) are first guesses to be calibrated against the
game's icons and screenshots, which is why they are sliders.
"""

import math

import bpy
import mathutils

from . import data, game_lights, sky

SUN_NAME = "Charon Sun"
RIG_COLLECTION = "Charon Lighting"
SAVED_PROP = "charon_lighting_saved"

SPACE_CONTEXTS = {"SPACE", "STATION", "FREIGHTER", "ANOMALY", "DERELICT"}
WEATHER_LISTS = {"NORMAL": "day", "FIRESTORM": "day_firestorm",
                 "GRAVSTORM": "day_gravstorm"}


def smoothstep(e0, e1, x):
    if e1 <= e0:
        return 1.0 if x >= e1 else 0.0
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


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
        }
        # the sky tables hold display colours: Standard shows them as they
        # are, where Blender's default AgX washes a blue sky out to grey
        # (measured on the same render). Changeable in the panel.
        try:
            scene.view_settings.view_transform = "Standard"
            scene.view_settings.look = "None"
        except TypeError:
            pass
    scene.world = sky.ensure_world()
    _sun(scene, create=True).hide_viewport = False
    apply(scene)
    apply_game_lights(scene)


def disable(scene):
    """Take the rig out and give back the world and view it replaced."""
    sun = _sun(scene, create=False)
    if sun is not None:
        sun.hide_viewport = True
        sun.hide_render = True
    game_lights.set_visible(scene, False)
    from ..materials import emission
    emission.set_lamps(True)

    saved = scene.get(SAVED_PROP)
    if saved:
        saved = saved.to_dict() if hasattr(saved, "to_dict") else dict(saved)
        scene.world = bpy.data.worlds.get(saved.get("world", "")) or None
        view = scene.view_settings
        for key in ("view_transform", "look", "exposure", "gamma"):
            try:
                setattr(view, key, saved[key])
            except (KeyError, TypeError, ValueError):
                pass
        del scene[SAVED_PROP]


def _rig_collection(scene):
    coll = bpy.data.collections.get(RIG_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(RIG_COLLECTION)
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    return coll


def _sun(scene, create):
    obj = bpy.data.objects.get(SUN_NAME)
    if obj is None and create:
        light = bpy.data.lights.get(SUN_NAME) or bpy.data.lights.new(SUN_NAME, "SUN")
        obj = bpy.data.objects.new(SUN_NAME, light)
        obj.hide_select = True
        _rig_collection(scene).objects.link(obj)
    return obj


# Applying ---
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
    day = data.planet_entry(WEATHER_LISTS.get(s.weather, "day"), list_name,
                            s.day_index)
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


def apply(scene):
    s = scene.charon_lighting
    if not s.enabled or not data.available():
        return
    world = scene.world if scene.world and scene.world.name == sky.WORLD_NAME \
        else sky.ensure_world()
    if scene.world != world:
        scene.world = world
    sun_obj = _sun(scene, create=True)
    sun = sun_obj.data
    context = s.context

    if context == "PLANET":
        state = planet_state(s)
        toward = _planet_path(s.time_of_day, s.sun_heading, s.sun_max_elevation)
        # below the horizon the light that is left comes from the other side
        # (the night light), dimmed by `night_light`
        light_dir = toward if toward.z >= 0.0 else -toward
        night = state["w_night"]
        light_strength = s.sun_strength * (1.0 - night * (1.0 - s.night_light))
        sky.set_mode(world, "planet")
        sky.set_planet_gradient(world, data.scale(state["fog"], 0.6),
                                state["horizon"], state["sky"], state["upper"])
        sky.set_sun(world, toward, state["sun"], state["solar"], s.sun_disc_size,
                    s.sun_disc_strength * (1.0 - night), s.sun_halo * (1.0 - night))
        light_colour = state["light"]
    elif context in SPACE_CONTEXTS:
        entry = data.space_entry(s.space_set, s.space_index)
        g = data.sky_globals()
        lin = lambda key: data.to_linear(entry.get(key, (0, 0, 0)))   # noqa: E731
        toward = _sun_direction(s.sun_elevation, s.sun_heading)
        light_dir = toward
        light_strength = s.sun_strength
        sky.set_mode(world, "space")
        if context == "DERELICT":
            fog = data.to_linear(g.get("AbandonedFreighterFogColour", (0.03, 0.09, 0.19)))
            sky.set_space_gradient(world, data.scale(fog, 0.5), fog, data.scale(fog, 0.7))
            sky.set_nebula(world, [fog, fog, fog], s.nebula_strength * 0.3, s.star_strength)
        else:
            sky.set_space_gradient(world, data.scale(lin("BottomColour"), 0.15),
                                   data.scale(lin("MidColour"), 0.15),
                                   data.scale(lin("TopColour"), 0.15))
            sky.set_nebula(world, [lin("NebulaColour1"), lin("NebulaColour2"),
                                   lin("NebulaColour3")],
                           s.nebula_strength, s.star_strength)
        sky.set_sun(world, toward, lin("LightColour"), lin("CloudColour"),
                    s.sun_disc_size, s.sun_disc_strength, s.sun_halo * 0.5,
                    halo_power=400.0)
        light_colour = lin("LightColour")
    else:                                                        # CATALOGUE
        toward = _sun_direction(s.sun_elevation, s.sun_heading)
        light_dir = toward
        light_strength = s.sun_strength
        sky.set_mode(world, "hdri")
        sky.set_hdri(world, s.hdri, s.hdri_rotation)
        light_colour = (1.0, 1.0, 1.0)

    sky.set_strengths(world, s.ambient, s.sky_strength)

    sun.color = light_colour
    sun.energy = max(0.0, light_strength)
    sun.angle = math.radians(max(0.05, s.sun_disc_size))
    sun_obj.rotation_mode = "QUATERNION"
    sun_obj.rotation_quaternion = light_dir.to_track_quat("Z", "Y")
    sun_obj.hide_viewport = sun_obj.hide_render = light_strength <= 0.0

    if scene.view_settings.exposure != s.exposure:
        scene.view_settings.exposure = s.exposure

    game_lights.set_visible(scene, s.game_lights)


def apply_game_lights(scene, rebuild=False):
    """Switch the game lamp layer to match the settings. Kept out of apply():
    the emission switch touches every mesh, which is not something to do on
    each slider step."""
    from ..materials import emission
    s = scene.charon_lighting
    on = s.enabled and s.game_lights
    if on and (rebuild or game_lights.count() == 0):
        game_lights.rebuild(scene, s.game_light_power)
    game_lights.set_visible(scene, on)
    # one or the other lights the scene, never both
    emission.set_lamps(not on)
