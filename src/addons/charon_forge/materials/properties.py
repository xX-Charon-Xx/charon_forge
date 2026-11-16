"""Names the colour system shares with the asset files, shader nodes and objects.
Many are baked into asset files or saved scenes, so they can't be renamed here alone."""

# The four object properties the NMS_Colourise node group reads, in slot order
# (primary, secondary, ternary, quaternary).
SLOT_PROPS = ("nms_p", "nms_s", "nms_t", "nms_q")
SLOT_ORDER = ("p", "s", "t", "q")

# Name prefix of the colourise node group carried by every colourable material.
COLOURISE_GROUP = "NMS_Colourise"

# The finish a part shows (UserData >> 24); a switch in each material reads it.
# A missing property reads 0, the first slice.
PROP_FINISH = "nms_finish"

# Written by the pipeline onto every material: the game's MaterialClass and
# material flags. The emission pass reads them (see emission.py).
MAT_CLASS = "nms_class"
MAT_FLAGS = "nms_flags"

# On every mesh appended from the high res library: the object id it came from.
# Marks a part as high res, so the flat material code leaves it alone.
MESH_TAG = "nms_high_res_id"

# The packed colour/finish value on every part.
PROP_USER_DATA = "UserData"

# Readable labels, so the viewport overlay keeps showing colour/material names.
PROP_READONLY_COLOUR = "readonly:Colour"
PROP_READONLY_MATERIAL = "readonly:Material"

# The old hand-tuned finish preview nodes; kept only so the teardown
# can find them in scenes saved before the change.
LEGACY_FINISH_NODES_TAG = "nms_finish_nodes"
LEGACY_FINISH_NODE_LABEL = "NMS Finish"
LEGACY_FINISH_PROPS = ("nms_finish_rough", "nms_finish_metal", "nms_finish_polish",
                       "nms_finish_tint", "nms_finish_tint_mix")
