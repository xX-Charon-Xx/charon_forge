"""Fossil parts, built from the high res library.

Copies of the base builder addon's part_overrides/bone.py, bone_replacer.py
and message.py (for the fossil ids only). The addon's own classes import the
fbx out of its models/fossil_parts folder, and since they are what its
override table hands out for every FOS_ id, a fossil placed from the asset
browser, loaded from a save or rebuilt out of a group always came out low res
- none of those ever reach our placement code with the bone's own id.

These are the same classes with one change: the object is made over the
shared mesh from asset_browser/assets, falling back to the addon's fbx only
when the library has no model for the id or the builder is the addon's own
low res one.

How a fossil is stored, which these keep exactly as the addon does:

  - A bone's ObjectID is only its kind (FOS_SKULL, FOS_TAIL...); which bone it
    is - FOS_HEAD_AA, FOS_BI_TAIL_AC - is in its Message.
  - FossilBone is what builds a bone from its full id, and moves that id into
    the Message as it does (shuffle_ids).
  - FossilBoneReplacer is what a save's FOS_SKULL placeholder is read as. It
    builds the bone its Message names in its place.
  - FossilDisplay is the display cases and mounts, which carry a Message but
    are otherwise plain parts.

The classes are made per Part class (make_classes), because they have to be
subclasses of whichever Part the builder placing them uses: the base builder
addon's while it is loaded, so its panels and operators treat them as its
own, and ours when Charon Forge is on its own. install() registers them
through the override table's register_override hook, which wins over the
addon's built in table.
"""

import time
from copy import copy

import bpy

from .. import materials
from ..builder import asset_library, placement
from ..utils import base_builder_utils
from ..utils.fallbacks import overrides as fallback_overrides
from .part import Part

PROP_MESSAGE = Part.PROP_MESSAGE

# A save's placeholder bones - read as FossilBoneReplacer, which swaps in the
# bone named in their Message. The same list as the addon's override table.
PLACEHOLDER_IDS = ("FOS_HEAD", "FOS_SKULL", "FOS_LIMBS", "FOS_TAIL", "FOS_BODY")

# Display cases and mounts - the fossil half of the addon's MESSAGE list.
DISPLAY_IDS = (
    "FOS_BI",
    "FOS_BIRD",
    "FOS_BIRD_DIS",
    "FOS_BI_DIS",
    "FOS_BODY_DISP",
    "FOS_BODY_MNT",
    "FOS_GRUN",
    "FOS_GRUN_DIS",
    "FOS_LIMBS_DISP",
    "FOS_LIMBS_MNT",
    "FOS_QUAD",
    "FOS_QUAD_DIS",
    "FOS_SKULL_DISP",
    "FOS_SKULL_MNT",
    "FOS_TAIL_DISP",
    "FOS_TAIL_MNT",
    "FOS_WORM",
    "FOS_WORM_DIS",
)

# A bone's kind is its id without the last part, except for these three,
# which the game files under another name - see FossilBone.shuffle_ids.
KIND_RENAMES = (
    ("FOS_HEAD", "FOS_SKULL"),
    ("FOS_BI_TAIL", "FOS_TAIL"),
    ("FOS_BI_BODY", "FOS_BODY"),
)

# one set of classes per Part class, so an isinstance check against an earlier
# part still holds. Keyed by the class itself - a reloaded base builder addon
# brings a new Part class and gets a new set.
_classes = {}

# what install() registered, as (override module, {object_id: class})
_registered = []


# Ids ---
def get_bone_ids():
    """Every bone the high res library has a model for.

    Read off the library rather than off the addon's fossil_parts folder, so
    it holds without that addon too: every FOS_ model that is not a
    placeholder or a display case is a bone.
    """
    others = set(PLACEHOLDER_IDS) | set(DISPLAY_IDS)
    return sorted(
        object_id
        for object_id in asset_library.get_asset_index()
        if object_id.startswith(placement.FOSSIL_PREFIX) and object_id not in others
    )


def bone_kind(bone_id):
    """The ObjectID a bone is saved under: FOS_HEAD_AA -> FOS_SKULL."""
    stripped = "_".join(bone_id.split("_")[:-1])
    for game_name, kind in KIND_RENAMES:
        if game_name in stripped:
            stripped = stripped.replace(game_name, kind)
    return stripped


# Shared behaviour ---
class FossilMessage(object):
    """The Message a fossil part carries, and its object made high res.

    Mixed in front of a Part class by make_classes.
    """

    def __init__(
        self,
        object_id=None,
        bpy_object=None,
        builder_object=None,
        user_data=None,
        build_rigs=False,
    ):
        # A new part gets what the game gives it, the way a plain high res
        # part does in placement.add_part - not the Part class's flat 0.
        if bpy_object is None and user_data is None and object_id:
            user_data = materials.default_user_data(object_id.replace("^", ""))

        super(FossilMessage, self).__init__(
            object_id=object_id,
            bpy_object=bpy_object,
            builder_object=builder_object,
            user_data=user_data,
            build_rigs=build_rigs,
        )
        if PROP_MESSAGE not in self.object:
            self.object[PROP_MESSAGE] = ""

        if bpy_object is None and materials.is_high_res(self.object):
            # the asset may have been appended just now, with its own copies
            # of textures and of the colourise node group - see
            # placement.add_part
            materials.dedupe_appended_data()
            materials.prepare_materials(self.object.data.materials)

    @property
    def message(self):
        return self.object.get(PROP_MESSAGE, "")

    @message.setter
    def message(self, value):
        self.object[PROP_MESSAGE] = str(value)

    def serialise(self):
        data = super(FossilMessage, self).serialise()
        data[PROP_MESSAGE] = self.message
        return data

    @classmethod
    def deserialise_from_data(cls, data, *args, **kwargs):
        part = super(FossilMessage, cls).deserialise_from_data(data, *args, **kwargs)
        part.message = data.get(PROP_MESSAGE, "")
        return part

    def retrieve_object_from_id(self, object_id):
        """The object over the high res library's mesh, when there is one.

        The addon's own builder - the one put back for low res proxies - has
        no use_high_res, so it keeps getting the fbx it always did.
        """
        if getattr(self.builder, "use_high_res", False):
            bpy_object = placement.new_high_res_object(object_id)
            if bpy_object is not None:
                return bpy_object
        return super(FossilMessage, self).retrieve_object_from_id(object_id)


class FossilBoneMixin(FossilMessage):
    """A bone, built from its full id - the addon's BONE."""

    def __init__(self, *args, **kwargs):
        super(FossilBoneMixin, self).__init__(*args, **kwargs)
        # an existing bone is already split into its kind and Message
        if self.object_id not in PLACEHOLDER_IDS:
            self.shuffle_ids()

    @classmethod
    def deserialise_from_data(cls, data, *args, **kwargs):
        # The Message a bone is built with is its own id (shuffle_ids), but
        # Part.deserialise_from_data then writes the data's Message over it -
        # empty when the data holds the bone's full id, as it does here. The
        # addon's BONE lost the bone that way; the id goes in as the Message.
        if not data.get(PROP_MESSAGE):
            data = dict(data)
            data[PROP_MESSAGE] = str(data.get(Part.PROP_OBJECT_ID, "")).replace("^", "")
        return super(FossilBoneMixin, cls).deserialise_from_data(data, *args, **kwargs)

    def shuffle_ids(self):
        """Move the object ID into the Message field, and then strip the
        suffix from the ID itself."""
        self.message = copy(self.object_id)
        kind = bone_kind(self.object_id)
        self.object_id = kind
        self.snap_id = kind


class FossilBoneReplacerMixin(FossilMessage):
    """A save's placeholder bone - the addon's BONE_REPLACER."""

    @classmethod
    def deserialise_from_data(cls, data, builder_object, build_rigs=True, *args, **kwargs):
        """Build the bone the placeholder's Message names.

        The addon's class built the placeholder first and then deleted it for
        the bone. That is now a high res model appended and thrown straight
        away for every fossil in a save, so the bone is built directly and
        the placeholder only when there is no bone named.
        """
        bone_id = str(data.get(PROP_MESSAGE, "") or "").replace("^", "")
        if not bone_id:
            return super(FossilBoneReplacerMixin, cls).deserialise_from_data(
                data, builder_object, build_rigs, *args, **kwargs
            )

        # the save keeps the colour on the placeholder, so carry it across or
        # every fossil comes out on the default palette
        bone_part = placement.add_part(
            builder_object,
            bone_id,
            user_data=data.get(Part.PROP_USER_DATA, 0),
            build_rigs=build_rigs,
            high_res=getattr(builder_object, "use_high_res", False),
        )

        pos = data.get(Part.PROP_POSITION, [0.0, 0.0, 0.0])
        up = data.get(Part.PROP_UP, [0.0, 0.0, 0.0])
        at = data.get(Part.PROP_AT, [0.0, 0.0, 0.0])
        world_matrix = cls.create_matrix_from_vectors(pos, up, at)
        bone_part.matrix_world = world_matrix
        bone_part.rotation = world_matrix.to_euler()
        bone_part.time_stamp = str(data.get(Part.PROP_TIMESTAMP, int(time.time())))
        bone_part.user_data = data.get(Part.PROP_USER_DATA, 0)
        return bone_part

    def swap_object(self):
        """Replace this placeholder with the bone its Message names."""
        bone_id = self.message
        if not bone_id:
            return None

        matrix = copy(self.object.matrix_world)
        user_data = self.object.get(Part.PROP_USER_DATA, 0)

        for child in list(self.object.children):
            bpy.data.objects.remove(child, do_unlink=True)
        bpy.data.objects.remove(self.object, do_unlink=True)

        bone_part = placement.add_part(
            self.builder,
            bone_id,
            user_data=user_data,
            high_res=getattr(self.builder, "use_high_res", False),
        )
        bone_part.object.matrix_world = matrix
        return bone_part


# Classes ---
def make_classes(part_class):
    """The fossil classes, as subclasses of a builder's Part class.

    Returns:
        tuple: (FossilBone, FossilBoneReplacer, FossilDisplay).
    """
    classes = _classes.get(part_class)
    if classes is None:
        classes = tuple(
            type(name, (mixin, part_class), {"__module__": __name__, "__doc__": mixin.__doc__})
            for name, mixin in (
                ("FossilBone", FossilBoneMixin),
                ("FossilBoneReplacer", FossilBoneReplacerMixin),
                ("FossilDisplay", FossilMessage),
            )
        )
        _classes[part_class] = classes
    return classes


def _class_table(part_class):
    """{object_id: class} for every fossil id."""
    bone_class, replacer_class, display_class = make_classes(part_class)
    table = {object_id: bone_class for object_id in get_bone_ids()}
    table.update({object_id: display_class for object_id in DISPLAY_IDS})
    # placeholders last - FOS_BODY and friends are in the addon's MESSAGE list
    # too, and the replacer is the one its table picks for them
    table.update({object_id: replacer_class for object_id in PLACEHOLDER_IDS})
    return table


def _register(module, part_class):
    table = _class_table(part_class)
    for object_id, class_ref in table.items():
        module.register_override(class_ref, [object_id])
    _registered.append((module, table))


# Install ---
def _host_modules():
    """The base builder addon's (builder.overrides, Part class), or None."""
    overrides_module = base_builder_utils.get_module("builder.overrides")
    part_module = base_builder_utils.get_module("part")
    part_class = getattr(part_module, "Part", None)
    if overrides_module is None or part_class is None:
        return None
    if not hasattr(overrides_module, "register_override"):
        return None
    return overrides_module, part_class


def install():
    """Register the fossil classes, ahead of the base builder addon's own.

    Always into Charon Forge's own override table, which is what is read
    while that addon isn't loaded, and into the addon's while it is.

    Returns:
        bool: True once the addon's table has them, or there is no addon.
    """
    remove()
    _register(fallback_overrides, Part)

    host = _host_modules()
    if host is None:
        return not base_builder_utils.is_available()
    overrides_module, host_part_class = host
    _register(overrides_module, host_part_class)
    return True


def is_installed():
    """False once the base builder addon has been reloaded and dropped ours."""
    host = _host_modules()
    if host is None:
        return True
    overrides_module, host_part_class = host
    replacer_class = make_classes(host_part_class)[1]
    return overrides_module.get_override_class(PLACEHOLDER_IDS[0]) is replacer_class


def remove():
    """Take the fossil classes back out, leaving whatever else is registered."""
    while _registered:
        module, table = _registered.pop()
        try:
            ours = [
                object_id for object_id, class_ref in table.items()
                if module.get_override_class(object_id) is class_ref
            ]
            module.unregister_override(ours)
        except (AttributeError, ReferenceError):
            pass
