"""The "Charon Sky" world: the game's skies as one node tree.

Three skies share the tree and a Mix picks one, so switching context never
rebuilds anything - it only changes node values:

    planet   a gradient on the view's height: fog colour below the horizon,
             HorizonColour at it, SkyColour above, SkyUpperColour at the
             zenith; plus the sun disc (SunColour) and its halo
             (SkySolarColour)
    space    the space entry's Bottom / Mid / Top gradient, the game's nebula
             dome (spacedome01: R, G and B are three masks, tinted with
             NebulaColour3, 1 and 2), procedural stars and the sun disc
    hdri     one of the game's HDRIs (the catalogue / studio look)

The same colour lights the scene and is what the camera sees, at two separate
strengths: Light Path > Is Camera Ray picks `visible` for camera rays and
`ambient` for everything else. That is how the game treats it too - its
ambient is the sky scaled by AmbientFactor, drawn separately from the sky.

Every node the rig changes has a fixed name (N_*), and set_* below write
straight into them. The tree is rebuilt only when SKY_VERSION changes.
"""

import math

import bpy

from . import data

WORLD_NAME = "Charon Sky"
SKY_VERSION = 1
VERSION_TAG = "charon_sky_version"

N_PLANET_RAMP = "CH planet ramp"
N_SPACE_RAMP = "CH space ramp"
N_SUN_DIR = "CH sun direction"
N_SUN_COLOUR = "CH sun colour"
N_HALO_COLOUR = "CH halo colour"
N_DISC_RANGE = "CH sun disc"
N_DISC_STRENGTH = "CH sun disc strength"
N_HALO_POWER = "CH halo power"
N_HALO_STRENGTH = "CH halo strength"
N_NEBULA = ("CH nebula 1", "CH nebula 2", "CH nebula 3")
N_NEBULA_STRENGTH = "CH nebula strength"
N_STAR_STRENGTH = "CH star strength"
N_DOME = "CH space dome"
N_HDRI = "CH hdri"
N_HDRI_MAPPING = "CH hdri mapping"
N_MIX_SPACE = "CH mix space"
N_MIX_HDRI = "CH mix hdri"
N_AMBIENT = "CH ambient"
N_VISIBLE = "CH visible"


# Building ---
def ensure_world():
    world = bpy.data.worlds.get(WORLD_NAME)
    if world is None:
        world = bpy.data.worlds.new(WORLD_NAME)
    if world.get(VERSION_TAG) != SKY_VERSION or not _complete(world):
        _build(world)
        world[VERSION_TAG] = SKY_VERSION
    return world


def _complete(world):
    tree = world.node_tree
    return tree is not None and all(
        tree.nodes.get(n) is not None
        for n in (N_PLANET_RAMP, N_SPACE_RAMP, N_SUN_DIR, N_MIX_SPACE,
                  N_MIX_HDRI, N_AMBIENT, N_VISIBLE, N_DOME, N_HDRI))


def _socket(sockets, identifier):
    """Mix nodes carry a float, vector and colour socket under one name; the
    identifier tells them apart."""
    for s in sockets:
        if s.identifier == identifier:
            return s
    raise KeyError(identifier)


def _build(world):
    try:
        world.use_nodes = True           # deprecated in 5.x, needed before
    except (AttributeError, TypeError):
        pass
    tree = world.node_tree
    tree.nodes.clear()
    nodes, links = tree.nodes, tree.links

    def node(kind, name=None, x=0, y=0, label=None):
        n = nodes.new(kind)
        if name:
            n.name = name
            n.label = label or name[3:]
        elif label:
            n.label = label
        n.location = (x, y)
        return n

    def vmath(op, x, y, name=None):
        n = node("ShaderNodeVectorMath", name, x, y)
        n.operation = op
        return n

    def math_node(op, x, y, name=None):
        n = node("ShaderNodeMath", name, x, y)
        n.operation = op
        return n

    def value(name, v, x, y):
        n = node("ShaderNodeValue", name, x, y)
        n.outputs[0].default_value = v
        return n

    def rgb(name, x, y):
        return node("ShaderNodeRGB", name, x, y)

    def mix_colour(name, x, y, blend="MIX"):
        n = node("ShaderNodeMix", name, x, y)
        n.data_type = "RGBA"
        n.blend_type = blend
        n.clamp_result = False
        return n

    # view direction -> height 0..1 ---
    coord = node("ShaderNodeTexCoord", x=-1800, y=0)
    direction = vmath("NORMALIZE", -1600, 0)
    links.new(coord.outputs["Generated"], direction.inputs[0])
    split = node("ShaderNodeSeparateXYZ", x=-1400, y=200)
    links.new(direction.outputs["Vector"], split.inputs[0])
    height = node("ShaderNodeMapRange", x=-1200, y=200, label="Height 0..1")
    height.inputs["From Min"].default_value = -1.0
    height.inputs["From Max"].default_value = 1.0
    links.new(split.outputs["Z"], height.inputs["Value"])

    planet_ramp = node("ShaderNodeValToRGB", N_PLANET_RAMP, -1000, 500)
    space_ramp = node("ShaderNodeValToRGB", N_SPACE_RAMP, -1000, 150)
    for ramp, count in ((planet_ramp, 4), (space_ramp, 3)):
        elements = ramp.color_ramp.elements
        while len(elements) < count:
            elements.new(0.5)
        ramp.color_ramp.interpolation = "EASE"
        links.new(height.outputs["Result"], ramp.inputs["Fac"])

    # the sun: disc and halo from the angle to it ---
    sun_dir = node("ShaderNodeCombineXYZ", N_SUN_DIR, -1400, -300)
    cos_angle = vmath("DOT_PRODUCT", -1200, -300)
    links.new(direction.outputs["Vector"], cos_angle.inputs[0])
    links.new(sun_dir.outputs["Vector"], cos_angle.inputs[1])
    disc = node("ShaderNodeMapRange", N_DISC_RANGE, -1000, -250)
    disc.clamp = True
    links.new(cos_angle.outputs["Value"], disc.inputs["Value"])
    halo_base = math_node("MAXIMUM", -1000, -450)
    halo_base.inputs[1].default_value = 0.0
    links.new(cos_angle.outputs["Value"], halo_base.inputs[0])
    halo = math_node("POWER", -800, -450, N_HALO_POWER)
    links.new(halo_base.outputs[0], halo.inputs[0])

    sun_colour = rgb(N_SUN_COLOUR, -1000, -650)
    halo_colour = rgb(N_HALO_COLOUR, -1000, -850)
    disc_strength = value(N_DISC_STRENGTH, 20.0, -800, -250)
    halo_strength = value(N_HALO_STRENGTH, 0.3, -800, -600)
    disc_amount = math_node("MULTIPLY", -600, -250)
    links.new(disc.outputs["Result"], disc_amount.inputs[0])
    links.new(disc_strength.outputs[0], disc_amount.inputs[1])
    halo_amount = math_node("MULTIPLY", -600, -450)
    links.new(halo.outputs[0], halo_amount.inputs[0])
    links.new(halo_strength.outputs[0], halo_amount.inputs[1])
    disc_rgb = vmath("SCALE", -400, -250)
    links.new(sun_colour.outputs[0], disc_rgb.inputs[0])
    links.new(disc_amount.outputs[0], disc_rgb.inputs["Scale"])
    halo_rgb = vmath("SCALE", -400, -450)
    links.new(halo_colour.outputs[0], halo_rgb.inputs[0])
    links.new(halo_amount.outputs[0], halo_rgb.inputs["Scale"])
    sun_rgb = vmath("ADD", -200, -350)
    links.new(disc_rgb.outputs[0], sun_rgb.inputs[0])
    links.new(halo_rgb.outputs[0], sun_rgb.inputs[1])

    planet = vmath("ADD", -200, 450)
    links.new(planet_ramp.outputs["Color"], planet.inputs[0])
    links.new(sun_rgb.outputs[0], planet.inputs[1])

    # space: gradient + nebula dome + stars + sun ---
    dome = node("ShaderNodeTexEnvironment", N_DOME, -1400, -1100)
    links.new(direction.outputs["Vector"], dome.inputs["Vector"])
    path = data.spacedome_path()
    if path:
        dome.image = bpy.data.images.load(path, check_existing=True)
        dome.image.colorspace_settings.name = "Non-Color"
    masks = node("ShaderNodeSeparateColor", x=-1150, y=-1100)
    links.new(dome.outputs["Color"], masks.inputs[0])
    nebula_sum = None
    # R -> NebulaColour3, G -> NebulaColour1, B -> NebulaColour2
    for i, (channel, name) in enumerate((("Red", N_NEBULA[2]),
                                         ("Green", N_NEBULA[0]),
                                         ("Blue", N_NEBULA[1]))):
        tint = rgb(name, -1000, -950 - 200 * i)
        part = vmath("SCALE", -800, -1000 - 200 * i)
        links.new(tint.outputs[0], part.inputs[0])
        links.new(masks.outputs[channel], part.inputs["Scale"])
        if nebula_sum is None:
            nebula_sum = part
        else:
            add = vmath("ADD", -600, -1000 - 200 * i)
            links.new(nebula_sum.outputs[0], add.inputs[0])
            links.new(part.outputs[0], add.inputs[1])
            nebula_sum = add
    nebula_strength = value(N_NEBULA_STRENGTH, 1.0, -600, -1500)
    nebula = vmath("SCALE", -400, -1100)
    links.new(nebula_sum.outputs[0], nebula.inputs[0])
    links.new(nebula_strength.outputs[0], nebula.inputs["Scale"])

    stars_map = node("ShaderNodeTexVoronoi", x=-1400, y=-1700, label="Stars")
    stars_map.voronoi_dimensions = "3D"
    stars_map.inputs["Scale"].default_value = 400.0
    links.new(direction.outputs["Vector"], stars_map.inputs["Vector"])
    star_core = node("ShaderNodeMapRange", x=-1150, y=-1650, label="Star size")
    star_core.inputs["From Min"].default_value = 0.0
    star_core.inputs["From Max"].default_value = 0.06
    star_core.inputs["To Min"].default_value = 1.0
    star_core.inputs["To Max"].default_value = 0.0
    links.new(stars_map.outputs["Distance"], star_core.inputs["Value"])
    star_pick = node("ShaderNodeSeparateColor", x=-1150, y=-1850)
    links.new(stars_map.outputs["Color"], star_pick.inputs[0])
    star_keep = math_node("GREATER_THAN", -950, -1850)
    star_keep.inputs[1].default_value = 0.8
    links.new(star_pick.outputs["Red"], star_keep.inputs[0])
    star = math_node("MULTIPLY", -800, -1700)
    links.new(star_core.outputs["Result"], star.inputs[0])
    links.new(star_keep.outputs[0], star.inputs[1])
    star_strength = value(N_STAR_STRENGTH, 2.0, -800, -1900)
    star_value = math_node("MULTIPLY", -600, -1700)
    links.new(star.outputs[0], star_value.inputs[0])
    links.new(star_strength.outputs[0], star_value.inputs[1])

    space = vmath("ADD", -200, 100)
    links.new(space_ramp.outputs["Color"], space.inputs[0])
    links.new(nebula.outputs[0], space.inputs[1])
    space_stars = vmath("ADD", 0, 50)
    links.new(space.outputs[0], space_stars.inputs[0])
    links.new(star_value.outputs[0], space_stars.inputs[1])
    space_sun = vmath("ADD", 200, 50)
    links.new(space_stars.outputs[0], space_sun.inputs[0])
    links.new(sun_rgb.outputs[0], space_sun.inputs[1])

    # hdri ---
    hdri_map = node("ShaderNodeMapping", N_HDRI_MAPPING, -1400, 900)
    hdri_map.vector_type = "POINT"
    links.new(direction.outputs["Vector"], hdri_map.inputs["Vector"])
    hdri = node("ShaderNodeTexEnvironment", N_HDRI, -1100, 900)
    links.new(hdri_map.outputs["Vector"], hdri.inputs["Vector"])

    # pick one, light with it ---
    mix_space = mix_colour(N_MIX_SPACE, 400, 300)
    links.new(planet.outputs[0], _socket(mix_space.inputs, "A_Color"))
    links.new(space_sun.outputs[0], _socket(mix_space.inputs, "B_Color"))
    mix_hdri = mix_colour(N_MIX_HDRI, 600, 300)
    links.new(_socket(mix_space.outputs, "Result_Color"),
              _socket(mix_hdri.inputs, "A_Color"))
    links.new(hdri.outputs["Color"], _socket(mix_hdri.inputs, "B_Color"))

    light_path = node("ShaderNodeLightPath", x=400, y=-200)
    ambient = value(N_AMBIENT, 1.0, 400, -500)
    visible = value(N_VISIBLE, 1.0, 400, -600)
    strength = node("ShaderNodeMix", x=650, y=-300, label="Camera sees / lights")
    strength.data_type = "FLOAT"
    links.new(light_path.outputs["Is Camera Ray"],
              _socket(strength.inputs, "Factor_Float"))
    links.new(ambient.outputs[0], _socket(strength.inputs, "A_Float"))
    links.new(visible.outputs[0], _socket(strength.inputs, "B_Float"))

    background = node("ShaderNodeBackground", x=900, y=200)
    links.new(_socket(mix_hdri.outputs, "Result_Color"), background.inputs["Color"])
    links.new(_socket(strength.outputs, "Result_Float"), background.inputs["Strength"])
    output = node("ShaderNodeOutputWorld", x=1100, y=200)
    links.new(background.outputs["Background"], output.inputs["Surface"])


# Setting ---
def _nodes(world):
    return world.node_tree.nodes


def _rgba(rgb):
    return (rgb[0], rgb[1], rgb[2], 1.0)


def set_mode(world, mode):
    """'planet', 'space' or 'hdri'."""
    nodes = _nodes(world)
    _socket(nodes[N_MIX_SPACE].inputs, "Factor_Float").default_value = \
        1.0 if mode == "space" else 0.0
    _socket(nodes[N_MIX_HDRI].inputs, "Factor_Float").default_value = \
        1.0 if mode == "hdri" else 0.0


def set_planet_gradient(world, ground, horizon, sky, upper):
    elements = _nodes(world)[N_PLANET_RAMP].color_ramp.elements
    for element, pos, colour in zip(elements, (0.0, 0.5, 0.56, 1.0),
                                    (ground, horizon, sky, upper)):
        element.position = pos
        element.color = _rgba(colour)


def set_space_gradient(world, bottom, mid, top):
    elements = _nodes(world)[N_SPACE_RAMP].color_ramp.elements
    for element, pos, colour in zip(elements, (0.0, 0.5, 1.0), (bottom, mid, top)):
        element.position = pos
        element.color = _rgba(colour)


def set_nebula(world, colours, strength, stars):
    nodes = _nodes(world)
    for name, colour in zip(N_NEBULA, colours):
        nodes[name].outputs[0].default_value = _rgba(colour)
    nodes[N_NEBULA_STRENGTH].outputs[0].default_value = strength
    nodes[N_STAR_STRENGTH].outputs[0].default_value = stars


def set_sun(world, direction, colour, halo_colour, disc_degrees, disc_strength,
            halo_strength, halo_power=64.0):
    nodes = _nodes(world)
    d = nodes[N_SUN_DIR]
    for i, v in enumerate(direction):
        d.inputs[i].default_value = v
    nodes[N_SUN_COLOUR].outputs[0].default_value = _rgba(colour)
    nodes[N_HALO_COLOUR].outputs[0].default_value = _rgba(halo_colour)
    size = math.radians(max(0.01, disc_degrees))
    disc = nodes[N_DISC_RANGE]
    disc.inputs["From Min"].default_value = math.cos(size)
    disc.inputs["From Max"].default_value = math.cos(size * 0.7)
    nodes[N_DISC_STRENGTH].outputs[0].default_value = disc_strength
    nodes[N_HALO_STRENGTH].outputs[0].default_value = halo_strength
    nodes[N_HALO_POWER].inputs[1].default_value = halo_power


def set_hdri(world, name, rotation_degrees):
    nodes = _nodes(world)
    node = nodes[N_HDRI]
    if name:
        path = data.hdri_path(name)
        if node.image is None or bpy.path.abspath(node.image.filepath) != path:
            try:
                node.image = bpy.data.images.load(path, check_existing=True)
            except RuntimeError as exc:
                print("Charon Forge: could not load HDRI %s: %r" % (name, exc))
    nodes[N_HDRI_MAPPING].inputs["Rotation"].default_value[2] = \
        math.radians(rotation_degrees)


def set_strengths(world, ambient, visible):
    nodes = _nodes(world)
    nodes[N_AMBIENT].outputs[0].default_value = ambient
    nodes[N_VISIBLE].outputs[0].default_value = visible
