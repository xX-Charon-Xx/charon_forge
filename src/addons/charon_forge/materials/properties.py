"""Names the colour system shares with the asset files, the shader nodes and
the objects it colours.

Kept in one place because most of them are baked into something outside this
package - the node group inside every asset file, or the materials of a scene
saved earlier - and cannot be renamed here alone.
"""

# The four object properties the NMS_Colourise node group reads, in slot order
# (primary, secondary, ternary, quaternary).
SLOT_PROPS = ("nms_p", "nms_s", "nms_t", "nms_q")

# The palette slots in their normal order, and under an inverting finish.
SLOT_ORDER = ("p", "s", "t", "q")
SLOT_ORDER_INVERTED = ("s", "p", "q", "t")

# Name prefix of the colourise node group carried by every asset file.
COLOURISE_GROUP = "NMS_Colourise"

# Object properties carrying the surface finish, read by the nodes
# finish_nodes.ensure_finish_nodes() splices into each colourable material.
# Both are offsets onto whatever the part's own texture maps say, so 0 - which
# is what an Attribute node reports for an object that has neither - means
# "exactly as the textures have it". That keeps every part that predates this
# unchanged.
PROP_FINISH_ROUGHNESS = "nms_finish_rough"
PROP_FINISH_METALLIC = "nms_finish_metal"

# How much of the part's own roughness to take away, 0..1.
#
# The library drives roughness from (1 - MASKS.red), and those maps are rough:
# sampled across the trims the median texel lands between 0.38 and 0.78. An
# offset can only ever add to that, so no amount of tuning the offsets could
# make a "gloss" or "polished" finish read as glossy, and a metallic finish
# came out as grey plastic - metal with no sharp reflection has very little
# else to show. This multiplies instead:
#
#     roughness = texture * (1 - polish) + offset
#
# Stored as the amount to REMOVE rather than a factor to multiply by, so that a
# missing property - which an Attribute node reports as 0 - still means "leave
# it exactly as the textures have it", the same invariant the offsets and the
# tint keep.
PROP_FINISH_POLISH = "nms_finish_polish"

# A colour the finish multiplies over the part, and how strongly.
# Kept as two properties rather than one RGBA so the "no tint" default needs
# no assumption about what an Attribute node reports for a missing alpha:
# a missing mix reads as 0, which is no tint at all.
PROP_FINISH_TINT = "nms_finish_tint"
PROP_FINISH_TINT_MIX = "nms_finish_tint_mix"

# Marks a material whose node tree has already had the finish nodes spliced
# in, so a second import does not stack a second copy on top. The value is the
# version below rather than True.
FINISH_NODES_TAG = "nms_finish_nodes"

# Bumped whenever the spliced network changes shape. A material carrying an
# older one - a scene saved before the change, whose materials came back with
# the file - is torn down and re-spliced rather than left on the old network.
FINISH_NODES_VERSION = 2

# Every node the splice adds is labelled with this, which is what lets the
# teardown find them again.
FINISH_NODE_LABEL = "NMS Finish"

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
