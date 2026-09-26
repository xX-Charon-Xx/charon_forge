"""Operators behind the "Proxy Quality" section of the Base Builder menu.

Switches every placed part and group in the scene between the high res
library and the old fbx proxies from the models folder, in place - same
transform, parent, collections and colour, just a different mesh source.
Group conversion itself lives in nms/group.py, next to the rest of the group
cache machinery it depends on.
"""

import contextlib
import sys

import bpy

from .. import builder as charon_builder
from .. import materials
from ..builder import paths, placement
from ..objects.forged import Forged
from ..objects.group import Group
from ..objects.part import Part
from ..utils import base_builder_utils


def _addon_module():
    """The addon's top level package module.

    This module sits one level under it (charon_forge.menu), so one rsplit of
    __package__ gets back to the addon itself.
    """
    return sys.modules[__package__.rsplit(".", 1)[0]]


@contextlib.contextmanager
def _suspend_scene_updates():
    """Pull the addon's own depsgraph handler out for the duration of a block. """
    addon_module = _addon_module()
    handler = getattr(addon_module, "udpates_handler", None)
    handlers = bpy.app.handlers.depsgraph_update_post
    was_registered = handler is not None and handler in handlers
    if was_registered:
        handlers.remove(handler)

    try:
        yield
    finally:
        if was_registered and handler not in handlers:
            handlers.append(handler)
        bpy.context.view_layer.update()


@contextlib.contextmanager
def _preserve_selection(context):
    """Put the selection and the active object back when the block is done."""
    view_layer = context.view_layer
    selected = list(context.selected_objects)
    active = view_layer.objects.active

    try:
        yield
    finally:
        for item in list(context.selected_objects):
            item.select_set(False)
        for item in selected:
            try:
                item.select_set(True)
            except (ReferenceError, RuntimeError):
                continue
        try:
            view_layer.objects.active = active
        except (ReferenceError, RuntimeError, TypeError):
            pass


def _switch_scene_parts(context, target_high_res, proxy_cache):
    """Point every ungrouped part in the scene at the other library's mesh.

    Nothing is rebuilt. Which library a part belongs to is entirely a property
    of the mesh datablock it points at, so switching one is a data assignment
    and a recolour: the object keeps its name, transform, parent, children,
    collections, selection and every custom property it had. That is not only
    far cheaper than replacing every object in the scene - one shared mesh per
    object id is looked up once and handed to every placement of it - it is
    also why a switch no longer disturbs anything else that referred to them.

    Groups carry a GroupID rather than an ObjectID, so they never match here -
    Group.switch_scene_proxy_quality handles those separately.

    Args:
        context: The context to read the scene from.
        target_high_res (bool): True to switch to the high res library, False to
            switch to the old fbx proxies.
        proxy_cache (dict): Carried across the whole switch - see
            builder.apply_proxy_mesh.

    Returns:
        tuple: (parts switched, parts the target library has no model for).
    """
    switched = 0
    missing_ids = []

    asset_index = charon_builder.asset_library.get_asset_index()
    to_colour = []

    # A snapshot, because importing a proxy the scene has not used yet links
    # the imported objects in before taking them out again.
    for source_object in list(context.scene.objects):
        if Part.PROP_OBJECT_ID not in source_object:
            continue
        if Group.PROP_GROUP_ID in source_object:
            continue
        # Only something with a mesh has a mesh to swap. The power line and
        # pipeline parts are curves, and handing one of those a mesh datablock
        # is an error rather than a switch.
        if source_object.type != "MESH":
            continue
        if materials.is_high_res(source_object) == target_high_res:
            continue

        object_id = source_object[Part.PROP_OBJECT_ID]
        user_data = source_object.get(Part.PROP_USER_DATA, Part.DEFAULT_USER_DATA)
        # a fossil bone shows the bone in its Message, not the kind in its
        # ObjectID - switching it by its ObjectID would swap in a generic bone
        model_id = placement.model_id_of(object_id, source_object.get(Part.PROP_MESSAGE))

        if target_high_res:
            new_mesh = charon_builder.load_high_res_mesh(model_id, asset_index)
            # An id the high res library does not cover - one of the ones it
            # still misses, or a mirrored part whose twin has no model of its
            # own. Left exactly as it is rather than swapped for something that
            # is not the part.
            if new_mesh is None:
                missing_ids.append(model_id)
                continue

            source_object.data = new_mesh
            to_colour.append((source_object, user_data))
        else:
            if not charon_builder.apply_proxy_mesh(
                source_object, model_id, user_data, cache=proxy_cache
            ):
                missing_ids.append(model_id)
                continue

        switched += 1

    if to_colour:
        # One pass over the lot, so each distinct UserData is decoded once
        materials.apply_many(to_colour)

    if missing_ids:
        # What _report_switch's "see the console" is pointing the user at.
        library = "high res" if target_high_res else "fbx proxy"
        print(
            "Charon Forge: no %s model for %d part(s), left as they were: %s"
            % (library, len(missing_ids), ", ".join(sorted(set(missing_ids))))
        )

    return switched, len(missing_ids)


def _switch_scene_proxies(context, target_high_res):
    """Switch every part and group in the scene to the requested quality.

    Runs with the addon's depsgraph handler detached and the selection held, so
    neither pass fires a curve resync per object touched or leaves the user's
    selection somewhere else when it is done.

    Args:
        context: The context to read the scene from.
        target_high_res (bool): True to switch to the high res library, False to
            switch to the old fbx proxies.

    Returns:
        tuple: (parts switched, groups switched, parts and groups that could
            not be switched).
    """
    # One cache for both passes: a group child and a placed part of the same
    # (ObjectID, UserData) want the same proxy mesh, so sharing it imports and
    # paints the fbx behind it once for the pair rather than once each. Across
    # calls the meshes themselves are found again by tag, so switching back and
    # forth does not cut a fresh set every time - see builder.apply_proxy_mesh.
    proxy_cache = {}

    with _suspend_scene_updates(), _preserve_selection(context):
        # The library-wide dedupe and finish passes are worth doing once for
        # the whole scene and are pure waste per part - see
        # materials.defer_shared_data.
        with materials.defer_shared_data():
            parts, missing = _switch_scene_parts(
                context, target_high_res, proxy_cache
            )
            groups, failed = Group.switch_scene_proxy_quality(
                context, charon_builder.get_builder(), target_high_res,
                proxy_cache=proxy_cache,
            )

        if target_high_res and (parts or groups):
            # Solid shading colours by MATERIAL out of the box and high res
            # parts share their materials, so without this whatever was just
            # switched is one flat grey mass until its textures load.
            materials.use_object_colour_in_viewport()

    return parts, groups, missing + failed


def _switch_builder_hook(target_high_res):
    """Match the base builder addon's active builder to the requested quality.

    Its own tools - the ones that place new parts, not just these two buttons -
    go through get_builder(), so this makes anything built afterwards follow
    the same quality that was just applied to the scene: our builder with the
    high res library layered on, or the addon's own builder for the plain fbx
    proxies it already knows how to place.
    """
    if target_high_res:
        host_builder = charon_builder.create_host_builder()
        if host_builder is not None:
            base_builder_utils.set_builder(host_builder)
    else:
        base_builder_utils.reset_builder()


def _report_switch(operator, parts, groups, skipped, quality):
    """Say what a switch actually did, including what it could not do."""
    if not parts and not groups:
        if skipped:
            operator.report(
                {"WARNING"},
                "Nothing switched - no %s model for %d part(s)." % (quality, skipped),
            )
        else:
            operator.report({"INFO"}, "Everything is already %s." % quality)
        return

    message = "Switched %d part(s) and %d group(s) to %s." % (parts, groups, quality)
    if skipped:
        # Named rather than silently counted as a success: a part with no model
        # in the target library is still sitting there at the other quality.
        operator.report(
            {"WARNING"}, "%s %d could not be switched - see the console." % (message, skipped)
        )
    else:
        operator.report({"INFO"}, message)


def set_proxy_quality(context, target_high_res):
    """Switch the scene and the base builder addon's active builder together.

    Shared by the two operators below and by the load_post handler in
    base_builder_menu.py that applies the preferences page's default quality
    whenever a blend file is opened.

    The result is recorded on scene.enum_proxy_quality, which is what the two
    buttons in the Base Builder dropdown show as pressed.

    Returns:
        tuple: (parts switched, groups switched, parts and groups that could
            not be switched) - see _switch_scene_proxies.
    """
    parts, groups, skipped = _switch_scene_proxies(context, target_high_res)
    _switch_builder_hook(target_high_res)

    scene = context.scene
    if scene is not None and hasattr(scene, "enum_proxy_quality"):
        scene.enum_proxy_quality = "high" if target_high_res else "low"

    return parts, groups, skipped


# Availability ---
SIMPLE_PROXIES = "Simple Proxies"


def simple_proxies_available():
    """True when there are fbx proxies to switch down to. Charon Forge ships
    none of its own - they are the base builder addon's (see
    paths.get_host_model_path)."""
    return paths.get_host_model_path() is not None


def simple_proxies_message():
    return base_builder_utils.missing_host_message(SIMPLE_PROXIES)


# Shapes ---
#
# Simple proxies hand the base builder addon its own builder back (see
# _switch_builder_hook), and that builder knows nothing of The Forge's shapes:
# it takes them for groups with no parts, so a save exported at low res would
# lose them without a word. Switching to low res therefore offers to split
# every shape into its parts first, and doesn't switch if that is declined.


def get_scene_shapes(scene):
    """Every shape made in The Forge in the scene."""
    return [obj for obj in scene.objects if Forged.is_forged(obj)]


def split_shapes(context, shapes):
    """Split shapes into their parts, each shape's parts gathered into a
    collection of their own - named after the shape, where the shape was - so
    they can still be picked out, moved or hidden as one later.

    Returns:
        tuple: (parts made, collections made).
    """
    builder_object = charon_builder.get_builder()
    part_count = 0
    collections = []
    # one texture and node group tidy for the lot, not one per shape
    with materials.defer_shared_data():
        for shape in shapes:
            # read before the split, which deletes the shape
            name = shape.name
            parent = shape.users_collection[0] if shape.users_collection else context.scene.collection

            parts = Forged.split(shape, builder_object)
            part_count += len(parts)
            if not parts:
                continue

            # Blender adds a .001 when the name is taken
            collection = bpy.data.collections.new(name)
            parent.children.link(collection)
            for part in parts:
                for old in list(part.users_collection):
                    old.objects.unlink(part)
                collection.objects.link(part)
            collections.append(collection)
    return part_count, collections


def offer_switch_to_low(delay=0.2):
    """Ask, in a popup, whether to split the scene's shapes and switch to
    low res - for switches that start without a window to ask in, like the
    one run when a file is opened."""
    def open_popup():
        window_manager = bpy.context.window_manager
        for window in window_manager.windows:
            for area in window.screen.areas:
                if area.type != "VIEW_3D":
                    continue
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                if region is None:
                    continue
                with bpy.context.temp_override(window=window, area=area, region=region):
                    bpy.ops.object.nms_switch_proxies_to_low("INVOKE_DEFAULT")
                return None
        return None

    bpy.app.timers.register(open_popup, first_interval=delay)


class NMS_OT_switch_proxies_to_low(bpy.types.Operator):
    """Switch every high res part and group in the scene to the old fbx proxy."""

    bl_idname = "object.nms_switch_proxies_to_low"
    bl_label = "Use Low-Res Proxies"
    bl_description = "Switch every high-res part and group in the scene to the old fbx proxy from the models folder"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        if not simple_proxies_available():
            self.report({"ERROR"}, simple_proxies_message())
            return {"CANCELLED"}
        # nothing to ask about without shapes
        if not get_scene_shapes(context.scene):
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(
            self, width=340, title="Switch to Simple Proxies",
            confirm_text="Split and Switch",
        )

    def draw(self, context):
        shape_count = len(get_scene_shapes(context.scene))
        layout = self.layout
        column = layout.column(align=True)
        column.label(
            text=f"This scene has {shape_count} shape(s) made in The Forge.",
            icon="ERROR",
        )
        column.separator()
        column.label(text="Simple proxies can't keep shapes - they would be", icon="BLANK1")
        column.label(text="left out when the base is exported.", icon="BLANK1")
        column.separator()
        column.label(text="Split them into individual parts and switch?", icon="BLANK1")
        column.label(text="Each shape's parts go in a collection of their own.", icon="BLANK1")
        column.label(text="Cancel leaves the scene as it is.", icon="BLANK1")

    def execute(self, context):
        if not simple_proxies_available():
            self.report({"ERROR"}, simple_proxies_message())
            return {"CANCELLED"}

        # Split and Switch; also what a script calling this directly gets
        shapes = get_scene_shapes(context.scene)
        split_parts, collections = split_shapes(context, shapes) if shapes else (0, [])

        parts, groups, skipped = set_proxy_quality(context, target_high_res=False)
        _report_switch(self, parts, groups, skipped, "low-res")
        if shapes:
            self.report(
                {"INFO"},
                "Split %d shape(s) into %d part(s), each in its own collection, "
                "then switched to low-res" % (len(collections), split_parts),
            )
        return {"FINISHED"}


class NMS_OT_switch_proxies_to_high(bpy.types.Operator):
    """Switch every old fbx proxy part and group in the scene to the high res library."""

    bl_idname = "object.nms_switch_proxies_to_high"
    bl_label = "Use High-Res Proxies"
    bl_description = "Switch every low-res proxy part and group in the scene to its the high res library part, where one exists"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        parts, groups, skipped = set_proxy_quality(context, target_high_res=True)
        _report_switch(self, parts, groups, skipped, "high-res")
        return {"FINISHED"}


class NMS_OT_fix_broken_textures(bpy.types.Operator):
    """Bring the scene up to date with this install: parts at the chosen proxy quality, every library part and its textures reimported."""

    bl_idname = "object.nms_fix_broken_textures"
    bl_label = "Fix Scene"
    bl_description = (
        "Reimport every library part and group, and reload every texture, from "
        "this install as it is now - picking up updated assets and textures. "
        "Also points missing textures at this install and switches anything not "
        "at the selected proxy quality to it"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ..builder import asset_library
        from ..materials import packing

        # proxies first: switching to high res appends assets, whose images
        # already point at this install, and relinking afterwards then only
        # has the file's own broken images left to fix
        target_high_res = context.scene.enum_proxy_quality == "high"
        low_res_unavailable = not target_high_res and not simple_proxies_available()
        if low_res_unavailable:
            # the scene is marked low res but there is nothing to switch
            # down to - fix the textures and leave the parts as they are
            parts = groups = skipped = 0
        else:
            parts, groups, skipped = set_proxy_quality(context, target_high_res)

        # then everything from the library again, as it is on disk now: the
        # parts' shared meshes, and the groups merged out of them
        reimported = rebuilt = 0
        failed = 0
        if target_high_res:
            with _suspend_scene_updates(), _preserve_selection(context):
                with materials.defer_shared_data():
                    reimported, failed = asset_library.reimport_library_meshes()
                    rebuilt, group_failed = Group.switch_scene_proxy_quality(
                        context, charon_builder.get_builder(), True, force=True,
                    )
                    failed += group_failed

        relinked, missing = packing.relink_library_textures()
        reloaded = packing.reload_library_textures()
        # every material through the same passes a fresh import gets
        materials.dedupe_appended_data()
        materials.prepare_materials()

        quality = "high-res" if target_high_res else "low-res"
        done = []
        if parts or groups:
            done.append("switched %d part(s) and %d group(s) to %s" % (parts, groups, quality))
        if reimported or rebuilt:
            done.append("reimported %d part(s) and %d group(s)" % (reimported, rebuilt))
        if reloaded:
            done.append("reloaded %d texture(s)" % reloaded)
        if relinked:
            done.append("fixed %d texture(s)" % relinked)
        if failed:
            skipped += failed
        problems = []
        if skipped:
            problems.append("%d part(s) or group(s) could not be loaded at %s "
                            "(see the console)" % (skipped, quality))
        if missing:
            problems.append("%d texture(s) have no match in the library" % missing)
        if low_res_unavailable:
            problems.append("parts left as they are: " + simple_proxies_message())

        if not done and not problems:
            self.report({"INFO"}, "Nothing to fix")
            return {"FINISHED"}

        message = ", ".join(done).capitalize() if done else "Nothing fixed"
        if problems:
            self.report({"WARNING"}, message + " - " + "; ".join(problems))
        else:
            self.report({"INFO"}, message)
        return {"FINISHED"}


classes = (
    NMS_OT_switch_proxies_to_low,
    NMS_OT_switch_proxies_to_high,
    NMS_OT_fix_broken_textures,
)
