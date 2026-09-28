"""The few places the base builder addon colours parts around its material hook.

Its Colour panel goes through the material provider for single parts, which
hooks.py already covers. The paths below don't, and most assume colour lives in
a flat material on the mesh, which is not how a high res part is coloured
(its colour is on the object, see materials/colouring.py):

  - Group.apply_colour writes whatever assign_material returns into EVERY
    material slot of a group. For a high res group ours returns None, since
    it recolours in place, so the group lost all of its materials.
  - NMSSettings.apply_default_colour does the same with
    assign_default_material for groups.
  - Group.group_objects merges the parts, which strips the palette
    properties the colourise node group reads, so a high res group came out
    blacked out until it was ungrouped. The wrapper puts the parts' colour
    back on, the way Charon Forge's own grouping does.
  - Curves paint only their first follower and expect the others to follow
    through the shared mesh. High res followers do share a mesh, but that
    mesh doesn't hold their colour, so only the first follower changed.

And two that aren't about colour: its Pin button calls
NMSSettings.deserialise_from_data with an argument it doesn't take, so
pinning a base always failed - see _wrap_deserialise_from_data. And its mirror
tool's mirror_correction, which gets the fit that places a mirrored part's
twin model where the flipped mesh was - see _wrap_mirror_correction.

Each colour path is wrapped here: high res objects go to Charon Forge's colouring and
everything else goes to the addon's own code, unchanged. remove() puts the
originals back.
"""

import sys

import bpy

from . import materials
from .builder import mirror_fit
from .objects.group import Group as CharonGroup
from .objects.part import Part
from .utils import base_builder_utils

# (owner, attribute name, the original as it sat in owner.__dict__)
_patched = []

_MARKER = "_charon_original"


def _patch(owner, name, make_wrapper, static=False):
    raw = owner.__dict__.get(name)
    if raw is None:
        return False
    original = raw.__func__ if isinstance(raw, staticmethod) else raw
    if hasattr(original, _MARKER):
        # left behind by an earlier load of this addon (a reload forgets
        # _patched): wrap the addon's own function again, not our old wrapper
        original = getattr(original, _MARKER)
        raw = staticmethod(original) if static else original
    wrapper = make_wrapper(original)
    setattr(wrapper, _MARKER, original)
    setattr(owner, name, staticmethod(wrapper) if static else wrapper)
    _patched.append((owner, name, raw))
    return True


# Groups ---
def _is_high_res_group(obj):
    return CharonGroup.PROP_GROUP_ID in obj and materials.is_high_res(obj)


def _group_default_user_data(group_obj):
    """What a group shows once its master colour is taken off: the colour
    most of its parts had, the same vote group_objects takes."""
    children, _ = CharonGroup.extract_cached_data(group_obj)
    counts = {}
    for cache_data in (children or {}).values():
        value = cache_data.get(CharonGroup.PROP_USER_DATA)
        if value is not None:
            counts[str(value)] = counts.get(str(value), 0) + 1
    if counts:
        return max(counts, key=counts.get)
    return materials.default_user_data(materials.object_id_of(group_obj))


def _wrap_group_apply_colour(original):
    def apply_colour(group_obj, colour_index, material_index):
        if _is_high_res_group(group_obj):
            # the recolour writes UserData onto the group, which is what makes
            # it the master colour its parts take on ungroup
            materials.recolour([group_obj], colour_index=colour_index,
                               material_index=material_index)
            return
        return original(group_obj, colour_index, material_index)
    return apply_colour


def _wrap_group_objects(original):
    def group_objects(objects_to_group, target_matrix=None):
        # read before the original deletes the parts
        parts = [
            obj for obj in (objects_to_group or [])
            if obj is not None and Part.PROP_OBJECT_ID in obj
            and CharonGroup.PROP_GROUP_ID not in obj
        ]
        colour_info = CharonGroup.get_colour_info(parts)
        merged_object = original(objects_to_group, target_matrix)
        if merged_object is not None:
            CharonGroup.carry_colour(merged_object, colour_info)
        return merged_object
    return group_objects


def _wrap_apply_default_colour(original):
    def apply_default_colour(self):
        selected = list(bpy.context.selected_objects)
        groups = [obj for obj in selected if _is_high_res_group(obj)]
        if not groups:
            return original(self)

        for group_obj in groups:
            if CharonGroup.PROP_USER_DATA in group_obj:
                del group_obj[CharonGroup.PROP_USER_DATA]
            materials.apply(group_obj, _group_default_user_data(group_obj))

        rest = [obj for obj in selected if obj not in groups]
        if not rest:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
            return None

        # the addon's own code for everything else, with the groups it would
        # break kept out of its sight
        for group_obj in groups:
            group_obj.select_set(False)
        try:
            return original(self)
        finally:
            for group_obj in groups:
                group_obj.select_set(True)
    return apply_default_colour


# Curves ---
def _sync_followers(curve_module, curve_obj):
    """Give every high res follower of a curve the curve's colour."""
    value = curve_obj.get("dup_UserData")
    if value is None:
        return
    children = curve_module.get_all_curve_children(curve_obj, require_id=False) or []
    high_res = [obj for obj in children if materials.is_high_res(obj)]
    if high_res:
        materials.recolour_from_user_data(high_res, value)


def _wrap_curve_apply_color(original, curve_module):
    def apply_color(curve_obj, user_data):
        result = original(curve_obj, user_data)
        if curve_obj is not None and "has_linked_objects" in curve_obj:
            _sync_followers(curve_module, curve_obj)
        return result
    return apply_color


def _wrap_apply_colour(original, curve_module):
    def apply_colour(self, colour_index=0, material=0):
        result = original(self, colour_index=colour_index, material=material)
        for obj in bpy.context.selected_objects:
            if "has_linked_objects" in obj and curve_module.is_bezier_or_nurbs_path(obj):
                _sync_followers(curve_module, obj)
        return result
    return apply_colour


# Pinning ---
def _wrap_deserialise_from_data(original, settings_class):
    """The addon's Pin button calls NMSSettings.deserialise_from_data with
    start_new_file=False, which the method doesn't take - so every pin
    raised a TypeError. False is meant to read the base's details in without
    new_file(), which empties the scene of every part."""
    def deserialise_from_data(self, nms_data, start_new_file=True):
        if start_new_file:
            return original(self, nms_data)
        new_file = settings_class.__dict__.get("new_file")
        settings_class.new_file = lambda _self: None
        try:
            return original(self, nms_data)
        finally:
            if new_file is None:
                del settings_class.new_file
            else:
                settings_class.new_file = new_file
    return deserialise_from_data


# Mirroring ---
def _mirror_twin_id(object_id):
    """The id the addon's mirror tool swaps a part to, or None when it leaves
    the part as it is. Its own rule (build_tool and Group.mirror_cache_data
    only swap to a twin it lists), so the fit is added only where the twin's
    model is what ends up shown."""
    host_part = getattr(base_builder_utils.get_module("part"), "Part", Part)
    twin_id = host_part.get_mirror_part_id(object_id)
    if twin_id is None:
        return None
    listed = getattr(base_builder_utils.get_module("tools.build_tool"),
                     "nice_name_dictionary", None)
    if listed is not None and twin_id not in listed:
        return None
    return twin_id


def _wrap_mirror_correction(original):
    """mirror_correction(object_id, matrix_world) is the last step of the
    addon's mirror transform, for a single part and for each part of a
    mirrored group. Its own corrections are hand tuned offsets for a few base
    parts; for a part whose twin has a high res model, the measured
    fit replaces them - see builder/mirror_fit.py."""
    def mirror_correction(object_id, matrix_world):
        object_id = str(object_id).replace("^", "")
        twin_id = _mirror_twin_id(object_id)
        fit = mirror_fit.fit(object_id, twin_id) if twin_id else None
        if fit is None:
            return original(object_id, matrix_world)
        return matrix_world @ fit
    return mirror_correction


# Install ---
def install():
    """Wrap the addon's colour paths. True once all of them are wrapped."""
    addon_name = base_builder_utils.get_addon_module_name()
    if addon_name is None:
        return False

    group_module = base_builder_utils.get_module("group")
    curve_module = base_builder_utils.get_module("utils.curve")
    settings_class = getattr(sys.modules.get(addon_name), "NMSSettings", None)

    done = True
    if group_module is not None and hasattr(group_module, "Group"):
        done &= _patch(group_module.Group, "apply_colour",
                       _wrap_group_apply_colour, static=True)
        done &= _patch(group_module.Group, "group_objects",
                       _wrap_group_objects, static=True)
    else:
        done = False

    if curve_module is not None:
        done &= _patch(curve_module, "apply_color",
                       lambda f: _wrap_curve_apply_color(f, curve_module))
    else:
        done = False

    if settings_class is not None:
        done &= _patch(settings_class, "apply_default_colour", _wrap_apply_default_colour)
        done &= _patch(settings_class, "deserialise_from_data",
                       lambda f: _wrap_deserialise_from_data(f, settings_class))
        if curve_module is not None:
            done &= _patch(settings_class, "apply_colour",
                           lambda f: _wrap_apply_colour(f, curve_module))
    else:
        done = False

    if not done:
        print("Charon Forge: some of the base builder addon's colour tools could "
              "not be hooked, they may not colour high res groups or curves")

    mirror_module = base_builder_utils.get_module("utils.mirror_utils")
    if mirror_module is None or not _patch(mirror_module, "mirror_correction",
                                           _wrap_mirror_correction):
        print("Charon Forge: the base builder addon's mirror tool could not be "
              "hooked, mirrored parts may move when a base is saved and loaded")
        done = False
    return done


def remove():
    """Put the addon's own functions back."""
    while _patched:
        owner, name, raw = _patched.pop()
        try:
            setattr(owner, name, raw)
        except (AttributeError, TypeError, ReferenceError):
            pass    # the addon went away first
