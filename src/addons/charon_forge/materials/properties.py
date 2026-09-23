"""Names the colour system shares with the asset files, the shader nodes and
the objects it colours.

Kept in one place because most of them are baked into something outside this
package - the node groups inside every asset file, or the materials of a scene
saved earlier - and cannot be renamed here alone. The asset side of each is
written by the extraction pipeline (its colourise and finishes phases).
"""

# The four object properties the NMS_Colourise node group reads, in slot order
# (primary, secondary, ternary, quaternary).
SLOT_PROPS = ("nms_p", "nms_s", "nms_t", "nms_q")
SLOT_ORDER = ("p", "s", "t", "q")

# Name prefix of the colourise node group carried by every colourable material.
COLOURISE_GROUP = "NMS_Colourise"

# The finish a part shows, as an object property: the finish index a save
# stores in UserData >> 24. Every finish-capable material in the library holds
# all of its texture set's slices (Concrete / Rust / Stone / Wood, Gloss /
# Inverted Gloss / Weathered / Metallic, ...) behind a switch reading this, so
# setting it IS applying the game's finish - its own diffuse, masks, normal
# and colourise mask. A missing property reads 0, the first slice.
PROP_FINISH = "nms_finish"

# Written by the pipeline onto every material: the game's MaterialClass and
# material flags. The emission pass reads them (see emission.py).
MAT_CLASS = "nms_class"
MAT_FLAGS = "nms_flags"

# Written onto every mesh appended from the high res library, holding the
# object id it came from. It marks a part as belonging to the new colour
# system, which is what the flat material code checks before deciding to paint
# a flat material over it.
MESH_TAG = "nms_high_res_id"

# The packed colour/finish value on every part.
PROP_USER_DATA = "UserData"

# Readable labels, so the viewport overlay keeps showing colour/material names.
PROP_READONLY_COLOUR = "readonly:Colour"
PROP_READONLY_MATERIAL = "readonly:Material"

# An earlier version previewed finishes by splicing roughness/metal/tint
# offsets in front of each Principled BSDF, driven by these properties and
# tuned by hand in finishes.json. The library now carries the game's own
# finish textures, so those nodes are torn out of any material that still has
# them (a scene saved before the change) and the properties are removed from
# its objects. Kept only so the teardown can find them.
LEGACY_FINISH_NODES_TAG = "nms_finish_nodes"
LEGACY_FINISH_NODE_LABEL = "NMS Finish"
LEGACY_FINISH_PROPS = ("nms_finish_rough", "nms_finish_metal", "nms_finish_polish",
                       "nms_finish_tint", "nms_finish_tint_mix")
