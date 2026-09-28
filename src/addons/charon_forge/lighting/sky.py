"""The "Charon Sky" world: the game's skies as one node tree.

Two skies share the tree and a Mix picks one, so switching never rebuilds
anything - it only changes node values:

    planet   a gradient on the view's height: fog colour below the horizon,
             HorizonColour at it, SkyColour above, SkyUpperColour at the
             zenith; plus the sun disc (SunColour) and its halo
             (SkySolarColour)
    space    the space entry's Bottom / Mid / Top gradient and its nebula:
               - the game's nebula dome (spacedome01: R, G, B are three
                 masks, tinted NebulaColour3, 1 and 2)
               - clouds: 4D noise, tinted NebulaColour2
               - wisps: the game's nebulaplasma filaments (alpha) threaded
                 through the clouds, tinted NebulaColour1
               - stars: bright ones, a field of faint ones, and a galaxy
                 band of dust where the faint ones crowd
               - the sun disc
             One number, the nebula shape (seed), turns the dome, moves the
             noise and the wisps and reseeds the stars - every seed with
             every one of the 58 colour entries is a different sky, the way
             the game makes its variety from one dome and a few colours.

The same colour lights the scene and is what the camera sees, at two separate
strengths: Light Path > Is Camera Ray picks `visible` for camera rays and
`ambient` for everything else.

Every node the rig changes has a fixed name (N_*), and set_* below write
straight into them. The tree is rebuilt only when SKY_VERSION changes.
"""

import math

import bpy

from . import data

WORLD_NAME = "Charon Sky"
SKY_VERSION = 3
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
N_CLOUD_STRENGTH = "CH cloud strength"
N_WISP_STRENGTH = "CH wisp strength"
N_STAR_STRENGTH = "CH star strength"
N_DOME = "CH space dome"
N_DOME_MAPPING = "CH dome turn"
N_NOISE = "CH cloud noise"
N_WISP = "CH wisps"
N_WISP_MAPPING = "CH wisp place"
N_STARS = "CH stars"
N_FIELD = "CH star field"
N_FIELD_STRENGTH = "CH star field strength"
N_BAND_AXIS = "CH galaxy axis"
N_BAND_NOISE = "CH galaxy dust"
N_BAND_STRENGTH = "CH galaxy strength"
N_BAND_COLOUR = "CH galaxy colour"
N_MIX_SPACE = "CH mix space"
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
                  N_AMBIENT, N_VISIBLE, N_DOME, N_NOISE, N_WISP, N_STARS,
                  N_FIELD, N_BAND_AXIS, N_BAND_NOISE))


def _socket(sockets, identifier):
    """Mix nodes carry a float, vector and colour socket under one name; the
    identifier tells them apart."""
    for s in sockets:
        if s.identifier == identifier:
            return s
    raise KeyError(identifier)


def _image(path, colorspace="Non-Color"):
    if not path:
        return None
    try:
        image = bpy.data.images.load(path, check_existing=True)
    except RuntimeError as exc:
        print("Charon Forge: could not load %s: %r" % (path, exc))
        return None
    image.colorspace_settings.name = colorspace
    return image


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

    def math_node(op, x, y, name=None, value=None):
        n = node("ShaderNodeMath", name, x, y)
        n.operation = op
        if value is not None:
            n.inputs[1].default_value = value
        return n

    def value(name, v, x, y):
        n = node("ShaderNodeValue", name, x, y)
        n.outputs[0].default_value = v
        return n

    def rgb(name, x, y):
        return node("ShaderNodeRGB", name, x, y)

    def scale(colour_socket, amount_socket, x, y):
        n = vmath("SCALE", x, y)
        links.new(colour_socket, n.inputs[0])
        links.new(amount_socket, n.inputs["Scale"])
        return n.outputs[0]

    def add(a, b, x, y):
        n = vmath("ADD", x, y)
        links.new(a, n.inputs[0])
        links.new(b, n.inputs[1])
        return n.outputs[0]

    def multiply(a, b, x, y):
        n = math_node("MULTIPLY", x, y)
        links.new(a, n.inputs[0])
        links.new(b, n.inputs[1])
        return n.outputs[0]

    # view direction -> height 0..1 ---
    coord = node("ShaderNodeTexCoord", x=-2400, y=0)
    direction = vmath("NORMALIZE", -2200, 0)
    links.new(coord.outputs["Generated"], direction.inputs[0])
    dir_out = direction.outputs["Vector"]
    split = node("ShaderNodeSeparateXYZ", x=-2000, y=200)
    links.new(dir_out, split.inputs[0])
    height = node("ShaderNodeMapRange", x=-1800, y=200, label="Height 0..1")
    height.inputs["From Min"].default_value = -1.0
    height.inputs["From Max"].default_value = 1.0
    links.new(split.outputs["Z"], height.inputs["Value"])

    planet_ramp = node("ShaderNodeValToRGB", N_PLANET_RAMP, -1000, 700)
    space_ramp = node("ShaderNodeValToRGB", N_SPACE_RAMP, -1000, 350)
    for ramp, count in ((planet_ramp, 4), (space_ramp, 3)):
        elements = ramp.color_ramp.elements
        while len(elements) < count:
            elements.new(0.5)
        ramp.color_ramp.interpolation = "EASE"
        links.new(height.outputs["Result"], ramp.inputs["Fac"])

    # the sun: disc and halo from the angle to it ---
    sun_dir = node("ShaderNodeCombineXYZ", N_SUN_DIR, -1400, -100)
    cos_angle = vmath("DOT_PRODUCT", -1200, -100)
    links.new(dir_out, cos_angle.inputs[0])
    links.new(sun_dir.outputs["Vector"], cos_angle.inputs[1])
    disc = node("ShaderNodeMapRange", N_DISC_RANGE, -1000, -50)
    disc.clamp = True
    links.new(cos_angle.outputs["Value"], disc.inputs["Value"])
    halo_base = math_node("MAXIMUM", -1000, -250, value=0.0)
    links.new(cos_angle.outputs["Value"], halo_base.inputs[0])
    halo = math_node("POWER", -800, -250, N_HALO_POWER)
    links.new(halo_base.outputs[0], halo.inputs[0])
    sun_colour = rgb(N_SUN_COLOUR, -1000, -450)
    halo_colour = rgb(N_HALO_COLOUR, -1000, -650)
    disc_strength = value(N_DISC_STRENGTH, 20.0, -800, -50)
    halo_strength = value(N_HALO_STRENGTH, 0.3, -800, -400)
    disc_rgb = scale(sun_colour.outputs[0],
                     multiply(disc.outputs["Result"], disc_strength.outputs[0], -600, -50),
                     -400, -50)
    halo_rgb = scale(halo_colour.outputs[0],
                     multiply(halo.outputs[0], halo_strength.outputs[0], -600, -250),
                     -400, -250)
    sun_rgb = add(disc_rgb, halo_rgb, -200, -150)

    planet = add(planet_ramp.outputs["Color"], sun_rgb, -200, 650)

    # space nebula: the game's dome, turned by the seed ---
    dome_turn = node("ShaderNodeMapping", N_DOME_MAPPING, -2000, -900)
    dome_turn.vector_type = "VECTOR"
    links.new(dir_out, dome_turn.inputs["Vector"])
    dome = node("ShaderNodeTexEnvironment", N_DOME, -1800, -900)
    dome.image = _image(data.spacedome_path())
    links.new(dome_turn.outputs["Vector"], dome.inputs["Vector"])
    masks = node("ShaderNodeSeparateColor", x=-1550, y=-900)
    links.new(dome.outputs["Color"], masks.inputs[0])
    tints = {name: rgb(name, -1350, -800 - 180 * i) for i, name in enumerate(N_NEBULA)}
    # R -> NebulaColour3, G -> NebulaColour1, B -> NebulaColour2
    dome_rgb = None
    for i, (channel, name) in enumerate((("Red", N_NEBULA[2]), ("Green", N_NEBULA[0]),
                                         ("Blue", N_NEBULA[1]))):
        part = scale(tints[name].outputs[0], masks.outputs[channel], -1150, -850 - 150 * i)
        dome_rgb = part if dome_rgb is None else add(dome_rgb, part, -950, -850 - 150 * i)

    # clouds: 4D noise, the seed is W ---
    noise = node("ShaderNodeTexNoise", N_NOISE, -1800, -1450)
    noise.noise_dimensions = "4D"
    noise.inputs["Scale"].default_value = 1.4
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.62
    links.new(dir_out, noise.inputs["Vector"])
    cloud_shape = node("ShaderNodeMapRange", x=-1550, y=-1450, label="Cloud edge")
    cloud_shape.inputs["From Min"].default_value = 0.48
    cloud_shape.inputs["From Max"].default_value = 0.78
    cloud_shape.clamp = True
    links.new(noise.outputs["Fac"], cloud_shape.inputs["Value"])
    cloud_mask = math_node("POWER", -1350, -1450, value=1.6)
    links.new(cloud_shape.outputs["Result"], cloud_mask.inputs[0])
    cloud_strength = value(N_CLOUD_STRENGTH, 0.35, -1350, -1600)
    clouds = scale(tints[N_NEBULA[1]].outputs[0],
                   multiply(cloud_mask.outputs[0], cloud_strength.outputs[0], -1150, -1450),
                   -950, -1450)

    # wisps: the game's nebulaplasma filaments on an equirect grid ---
    atan = math_node("ARCTAN2", -2000, -1850)
    links.new(split.outputs["Y"], atan.inputs[0])
    links.new(split.outputs["X"], atan.inputs[1])
    u = math_node("MULTIPLY", -1850, -1850, value=1.0 / (2.0 * math.pi))
    links.new(atan.outputs[0], u.inputs[0])
    asin = math_node("ARCSINE", -2000, -2000)
    links.new(split.outputs["Z"], asin.inputs[0])
    v = math_node("MULTIPLY", -1850, -2000, value=1.0 / math.pi)
    links.new(asin.outputs[0], v.inputs[0])
    uv = node("ShaderNodeCombineXYZ", x=-1700, y=-1900)
    links.new(u.outputs[0], uv.inputs["X"])
    links.new(v.outputs[0], uv.inputs["Y"])
    wisp_place = node("ShaderNodeMapping", N_WISP_MAPPING, -1550, -1900)
    wisp_place.inputs["Scale"].default_value = (4.0, 2.0, 1.0)
    links.new(uv.outputs["Vector"], wisp_place.inputs["Vector"])
    wisp = node("ShaderNodeTexImage", N_WISP, -1350, -1900)
    wisp.image = _image(data.nebulaplasma_path())
    wisp.extension = "REPEAT"
    links.new(wisp_place.outputs["Vector"], wisp.inputs["Vector"])
    wisp_amount = math_node("MULTIPLY", -1100, -1900)
    links.new(wisp.outputs["Alpha"], wisp_amount.inputs[0])
    links.new(cloud_shape.outputs["Result"], wisp_amount.inputs[1])
    wisp_strength = value(N_WISP_STRENGTH, 3.0, -1100, -2050)
    wisps = scale(tints[N_NEBULA[0]].outputs[0],
                  multiply(wisp_amount.outputs[0], wisp_strength.outputs[0], -950, -1900),
                  -800, -1900)

    nebula_strength = value(N_NEBULA_STRENGTH, 1.0, -800, -1300)
    nebula = scale(add(add(dome_rgb, clouds, -700, -1100), wisps, -600, -1300),
                   nebula_strength.outputs[0], -450, -1100)

    # stars, reseeded with the nebula ---
    stars_map = node("ShaderNodeTexVoronoi", N_STARS, -1800, -2350)
    stars_map.voronoi_dimensions = "4D"
    stars_map.inputs["Scale"].default_value = 400.0
    links.new(dir_out, stars_map.inputs["Vector"])
    star_core = node("ShaderNodeMapRange", x=-1550, y=-2300, label="Star size")
    star_core.inputs["From Min"].default_value = 0.0
    star_core.inputs["From Max"].default_value = 0.06
    star_core.inputs["To Min"].default_value = 1.0
    star_core.inputs["To Max"].default_value = 0.0
    links.new(stars_map.outputs["Distance"], star_core.inputs["Value"])
    star_pick = node("ShaderNodeSeparateColor", x=-1550, y=-2500)
    links.new(stars_map.outputs["Color"], star_pick.inputs[0])
    star_keep = math_node("GREATER_THAN", -1350, -2500, value=0.8)
    links.new(star_pick.outputs["Red"], star_keep.inputs[0])
    star_strength = value(N_STAR_STRENGTH, 2.0, -1350, -2650)
    star = multiply(multiply(star_core.outputs["Result"], star_keep.outputs[0], -1150, -2350),
                    star_strength.outputs[0], -950, -2350)

    # the star field: many small faint stars, crowded into the galaxy band ---
    field = node("ShaderNodeTexVoronoi", N_FIELD, -1800, -2900)
    field.voronoi_dimensions = "4D"
    field.inputs["Scale"].default_value = 1400.0
    links.new(dir_out, field.inputs["Vector"])
    field_core = node("ShaderNodeMapRange", x=-1550, y=-2850, label="Field star size")
    field_core.inputs["From Min"].default_value = 0.0
    field_core.inputs["From Max"].default_value = 0.1
    field_core.inputs["To Min"].default_value = 1.0
    field_core.inputs["To Max"].default_value = 0.0
    links.new(field.outputs["Distance"], field_core.inputs["Value"])
    field_pick = node("ShaderNodeSeparateColor", x=-1550, y=-3050)
    links.new(field.outputs["Color"], field_pick.inputs[0])
    field_keep = math_node("GREATER_THAN", -1350, -3050, value=0.55)
    links.new(field_pick.outputs["Red"], field_keep.inputs[0])
    field_star = multiply(field_core.outputs["Result"], field_keep.outputs[0], -1150, -2900)

    # the galaxy band: a great circle of dust and crowded stars ---
    band_axis = node("ShaderNodeCombineXYZ", N_BAND_AXIS, -1800, -3350)
    band_axis.inputs["Z"].default_value = 1.0
    band_dot = vmath("DOT_PRODUCT", -1600, -3350)
    links.new(dir_out, band_dot.inputs[0])
    links.new(band_axis.outputs["Vector"], band_dot.inputs[1])
    band_abs = math_node("ABSOLUTE", -1450, -3350)
    links.new(band_dot.outputs["Value"], band_abs.inputs[0])
    band_shape = node("ShaderNodeMapRange", x=-1300, y=-3350, label="Band width")
    band_shape.inputs["From Min"].default_value = 0.0
    band_shape.inputs["From Max"].default_value = 0.38
    band_shape.inputs["To Min"].default_value = 1.0
    band_shape.inputs["To Max"].default_value = 0.0
    band_shape.clamp = True
    links.new(band_abs.outputs[0], band_shape.inputs["Value"])
    band_soft = math_node("POWER", -1100, -3350, value=2.0)
    links.new(band_shape.outputs["Result"], band_soft.inputs[0])
    dust = node("ShaderNodeTexNoise", N_BAND_NOISE, -1600, -3600)
    dust.noise_dimensions = "4D"
    dust.inputs["Scale"].default_value = 4.0
    dust.inputs["Detail"].default_value = 10.0
    dust.inputs["Roughness"].default_value = 0.65
    links.new(dir_out, dust.inputs["Vector"])
    dust_shape = node("ShaderNodeMapRange", x=-1350, y=-3600, label="Dust")
    dust_shape.inputs["From Min"].default_value = 0.35
    dust_shape.inputs["From Max"].default_value = 0.75
    dust_shape.clamp = True
    links.new(dust.outputs["Fac"], dust_shape.inputs["Value"])
    band = multiply(band_soft.outputs[0], dust_shape.outputs["Result"], -950, -3450)
    band_strength = value(N_BAND_STRENGTH, 0.0, -950, -3650)
    band_colour = rgb(N_BAND_COLOUR, -950, -3800)
    band_rgb = scale(band_colour.outputs[0], multiply(band, band_strength.outputs[0], -750, -3500),
                     -550, -3500)
    # stars crowd into the band as it brightens
    crowd = math_node("MULTIPLY_ADD", -750, -3100)
    links.new(band, crowd.inputs[0])
    crowd.inputs[1].default_value = 8.0          # band x 8 + 1
    crowd.inputs[2].default_value = 1.0
    crowded = multiply(field_star, crowd.outputs[0], -550, -3000)
    field_strength = value(N_FIELD_STRENGTH, 0.3, -550, -3200)
    field_value = multiply(crowded, field_strength.outputs[0], -350, -3000)

    stars_all = math_node("ADD", -200, -2600)
    links.new(star, stars_all.inputs[0])
    links.new(field_value, stars_all.inputs[1])

    space = add(add(add(add(space_ramp.outputs["Color"], nebula, -200, 300), band_rgb, -100, 280),
                    stars_all.outputs[0], 0, 250), sun_rgb, 200, 250)

    # pick one, light with it ---
    mix_space = node("ShaderNodeMix", N_MIX_SPACE, 400, 400)
    mix_space.data_type = "RGBA"
    mix_space.clamp_result = False
    links.new(planet, _socket(mix_space.inputs, "A_Color"))
    links.new(space, _socket(mix_space.inputs, "B_Color"))

    light_path = node("ShaderNodeLightPath", x=400, y=-200)
    ambient = value(N_AMBIENT, 1.0, 400, -500)
    visible = value(N_VISIBLE, 1.0, 400, -600)
    strength = node("ShaderNodeMix", x=650, y=-300, label="Camera sees / lights")
    strength.data_type = "FLOAT"
    links.new(light_path.outputs["Is Camera Ray"], _socket(strength.inputs, "Factor_Float"))
    links.new(ambient.outputs[0], _socket(strength.inputs, "A_Float"))
    links.new(visible.outputs[0], _socket(strength.inputs, "B_Float"))

    background = node("ShaderNodeBackground", x=900, y=300)
    links.new(_socket(mix_space.outputs, "Result_Color"), background.inputs["Color"])
    links.new(_socket(strength.outputs, "Result_Float"), background.inputs["Strength"])
    output = node("ShaderNodeOutputWorld", x=1100, y=300)
    links.new(background.outputs["Background"], output.inputs["Surface"])


# Setting ---
def _nodes(world):
    return world.node_tree.nodes


def _rgba(rgb):
    return (rgb[0], rgb[1], rgb[2], 1.0)


def set_mode(world, mode):
    """'planet' or 'space'."""
    _socket(_nodes(world)[N_MIX_SPACE].inputs, "Factor_Float").default_value = \
        1.0 if mode == "space" else 0.0


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


def set_nebula(world, colours, strength, stars, clouds=0.35):
    nodes = _nodes(world)
    for name, colour in zip(N_NEBULA, colours):
        nodes[name].outputs[0].default_value = _rgba(colour)
    nodes[N_NEBULA_STRENGTH].outputs[0].default_value = strength
    nodes[N_CLOUD_STRENGTH].outputs[0].default_value = clouds
    nodes[N_WISP_STRENGTH].outputs[0].default_value = clouds * 8.0
    nodes[N_STAR_STRENGTH].outputs[0].default_value = stars


def set_nebula_shape(world, seed):
    """Seed 0 is the game's dome as it is; every other seed turns it, moves
    the clouds and wisps, and reseeds the stars."""
    nodes = _nodes(world)
    turn = nodes[N_DOME_MAPPING].inputs["Rotation"]
    turn.default_value = (math.radians((seed * 37) % 360) if seed else 0.0,
                          math.radians((seed * 23) % 360) if seed else 0.0,
                          math.radians((seed * 71) % 360))
    nodes[N_NOISE].inputs["W"].default_value = seed * 1.37
    nodes[N_WISP_MAPPING].inputs["Location"].default_value = (
        (seed * 0.318) % 1.0, (seed * 0.577) % 1.0, 0.0)
    nodes[N_STARS].inputs["W"].default_value = seed * 0.91
    nodes[N_FIELD].inputs["W"].default_value = seed * 0.53
    nodes[N_BAND_NOISE].inputs["W"].default_value = seed * 0.77
    # the galaxy band tilts with the seed: seed 0 lies close to the horizon
    tilt = math.radians(15.0 + (seed * 29) % 60) if seed else math.radians(20.0)
    turn = math.radians((seed * 53) % 360)
    axis = nodes[N_BAND_AXIS].inputs
    axis[0].default_value = math.sin(tilt) * math.cos(turn)
    axis[1].default_value = math.sin(tilt) * math.sin(turn)
    axis[2].default_value = math.cos(tilt)


def set_star_style(world, field, band, band_colour):
    """The star field's strength, the galaxy band's strength and colour."""
    nodes = _nodes(world)
    nodes[N_FIELD_STRENGTH].outputs[0].default_value = field
    nodes[N_BAND_STRENGTH].outputs[0].default_value = band
    nodes[N_BAND_COLOUR].outputs[0].default_value = _rgba(band_colour)


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


def set_strengths(world, ambient, visible):
    nodes = _nodes(world)
    nodes[N_AMBIENT].outputs[0].default_value = ambient
    nodes[N_VISIBLE].outputs[0].default_value = visible
