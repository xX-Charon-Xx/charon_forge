"""The game's own lamps as Blender lights, in one managed collection.

A part stays one object with no children. Its lamps - the LIGHT nodes of its
game scenes, which the pipeline already copies into resources/colours.json
(objects.<id>.lights: matrix, colour, intensity, radius, fov) - are made as
separate light objects in the "Charon Game Lights" collection. Each follows
its part through a Child Of constraint, not a parent, so moving the part moves
its lamps, and the whole layer can be deleted or rebuilt at any time
(`rebuild`).

Why real lights and not only glowing surfaces (materials/emission.py): EEVEE
does not light a room from emission unless raytracing is on, and even then
a lamp's few square centimetres of glowing surface are noisy. A point / spot
light does both engines the same way. While the layer is on, the emission
boost is switched off (emission.set_lamps) so a lamp is not counted twice.

Power: a game light reaches `intensity / d^2`; a Blender point light of P
watts matches that at P = 4 pi x intensity - the same scale the emission
boost uses. `power` (the panel's Glow) scales all of them at once.
"""

import math

import bpy
import mathutils

from . import data

COLLECTION_NAME = "Charon Game Lights"
LIGHT_TAG = "charon_game_light"
SPOT_MAX_FOV = 179.0


def _collection(scene, create):
    coll = bpy.data.collections.get(COLLECTION_NAME)
    if coll is None and create:
        coll = bpy.data.collections.new(COLLECTION_NAME)
    if coll is not None and create and coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    return coll


def clear(scene=None):
    coll = bpy.data.collections.get(COLLECTION_NAME)
    if coll is None:
        return 0
    removed = 0
    for obj in list(coll.objects):
        light = obj.data if obj.type == "LIGHT" else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if light is not None and light.users == 0:
            bpy.data.lights.remove(light)
        removed += 1
    return removed


def _part_lights(obj):
    """(object id, [game light]) of a Charon part, or None."""
    from ..materials import game_data
    from ..materials.properties import MESH_TAG

    if obj.type != "MESH" or obj.data is None:
        return None
    object_id = obj.data.get(MESH_TAG)
    if not object_id:
        return None
    lights = [l for l in (game_data.object_info(object_id).get("lights") or [])
              if not l.get("in_effect") and float(l.get("intensity", 0)) > 0]
    return (object_id, lights) if lights else None


def _light_data(object_id, light, power):
    """One light datablock per lamp of a part, shared by every copy of it."""
    name = "CH %s %s" % (object_id, light.get("name", "light"))
    fov = float(light.get("fov", 360.0))
    kind = "SPOT" if fov < SPOT_MAX_FOV else "POINT"
    lamp = bpy.data.lights.get(name)
    if lamp is None or lamp.type != kind:
        lamp = bpy.data.lights.new(name, kind)
    lamp[LIGHT_TAG] = float(light.get("intensity", 0.0))
    lamp.color = data.to_linear(light.get("colour", (1, 1, 1)))
    lamp.energy = 4.0 * math.pi * lamp[LIGHT_TAG] * power
    lamp.shadow_soft_size = 0.05
    if kind == "SPOT":
        lamp.spot_size = math.radians(max(1.0, fov))
        lamp.spot_blend = 0.3
    radius = float(light.get("radius", 0.0))
    if radius > 0 and hasattr(lamp, "use_custom_distance"):
        lamp.use_custom_distance = True
        lamp.cutoff_distance = radius
    return lamp


def rebuild(scene, power=1.0):
    """Every Charon part's game lamps, and nothing else, in the collection.

    Returns:
        int: How many lights were made.
    """
    clear(scene)
    coll = _collection(scene, create=True)
    made = 0
    for obj in scene.objects:
        found = _part_lights(obj)
        if found is None:
            continue
        object_id, lights = found
        for light in lights:
            lamp = _light_data(object_id, light, power)
            lamp_obj = bpy.data.objects.new(
                "%s · %s" % (obj.name, light.get("name", "light")), lamp)
            lamp_obj[LIGHT_TAG] = obj.name
            coll.objects.link(lamp_obj)
            # the game's matrix is in the part's own (model) space - the
            # space its mesh is in - so the part's world matrix places it
            m = light.get("matrix")
            if m and len(m) == 16:
                lamp_obj.matrix_basis = mathutils.Matrix(
                    [m[0:4], m[4:8], m[8:12], m[12:16]])
            else:
                lamp_obj.location = light.get("position", (0, 0, 0))
            follow = lamp_obj.constraints.new("CHILD_OF")
            follow.target = obj
            follow.inverse_matrix = mathutils.Matrix.Identity(4)
            lamp_obj.hide_select = True
            made += 1
    return made


def set_power(power):
    """Every lamp x power (the Glow slider). Only lamps whose value changes are
    written, so it costs nothing while another slider moves."""
    for lamp in bpy.data.lights:
        if LIGHT_TAG in lamp:
            energy = 4.0 * math.pi * lamp[LIGHT_TAG] * power
            if abs(lamp.energy - energy) > 1e-6:
                lamp.energy = energy


def set_visible(scene, visible):
    coll = _collection(scene, create=False)
    if coll is None:
        return
    # only on a change: setting the same flag still re-evaluates the scene
    if coll.hide_viewport == visible:
        coll.hide_viewport = not visible
    if coll.hide_render == visible:
        coll.hide_render = not visible


def count():
    coll = bpy.data.collections.get(COLLECTION_NAME)
    return len(coll.objects) if coll else 0
