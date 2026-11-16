import bpy
from bpy.props import StringProperty

from .. import builder as charon_builder
from ..objects.group import Group
from ..objects.part import Part
from ..utils import dictionary, loading_overlay, selection

# fossil bones have no variants
_FOSSIL_PREFIX = "FOS_"

# copied from the old part to the new one
_KEPT_PROPS = (Part.PROP_ORDER, Part.PROP_BELONGS_TO_PRESET)


def part_model_id(bpy_object):
    """The part's model id, or None if it isn't a part."""
    if bpy_object is None or Part.PROP_OBJECT_ID not in bpy_object:
        return None
    if "PresetID" in bpy_object or Group.PROP_GROUP_ID in bpy_object:
        return None
    object_id = str(bpy_object[Part.PROP_OBJECT_ID]).replace("^", "")
    if object_id.startswith(_FOSSIL_PREFIX):
        return None
    return str(bpy_object.get("nms_form_model") or object_id).replace("^", "")


def _move_into_place(new_object, old_object):
    """Give the new part the old one's collections, parent, children and position."""
    old_collections = list(old_object.users_collection)
    for collection in old_collections:
        if new_object.name not in collection.objects:
            collection.objects.link(new_object)
    for collection in list(new_object.users_collection):
        if collection not in old_collections:
            collection.objects.unlink(new_object)

    new_object.parent = old_object.parent
    new_object.matrix_parent_inverse = old_object.matrix_parent_inverse.copy()
    new_object.matrix_world = old_object.matrix_world.copy()

    for child in list(old_object.children):
        child_matrix = child.matrix_world.copy()
        child.parent = new_object
        child.matrix_world = child_matrix


class ReplaceWithVariant(bpy.types.Operator):
    bl_idname = "charon.replace_with_variant"
    bl_label = "Replace with Variant"
    bl_description = "Replace the active part with this variant, keeping its place and colour"
    bl_options = {"REGISTER", "UNDO"}

    object_id: StringProperty()

    @classmethod
    def description(cls, context, properties):
        name = dictionary.get_nice_names_diictionary().get(properties.object_id)
        name = dictionary.to_title_case(name) if name else properties.object_id
        return f"Replace the active part with {name}\nObjectID : {properties.object_id}"

    @classmethod
    def poll(cls, context):
        return part_model_id(context.active_object) is not None

    @loading_overlay.while_running("Replacing part")
    def execute(self, context):
        old_object = context.active_object
        current_id = part_model_id(old_object)
        variant_id = self.object_id.replace("^", "")
        if current_id is None:
            self.report({"WARNING"}, "The active object is not a part")
            return {"CANCELLED"}
        if variant_id == current_id:
            return {"CANCELLED"}
        if variant_id not in dictionary.get_variant_family(current_id):
            self.report({"ERROR"}, f"{variant_id} is not a variant of {current_id}")
            return {"CANCELLED"}

        # keep the part's colour
        try:
            user_data = int(old_object.get(Part.PROP_USER_DATA))
        except (TypeError, ValueError):
            user_data = None

        try:
            item = charon_builder.add_part(variant_id, user_data=user_data)
        except Exception as error:                        # noqa: BLE001
            self.report({"ERROR"}, f"Could not add {variant_id}: {error}")
            return {"CANCELLED"}
        new_object = getattr(item, "object", None)
        if new_object is None:
            self.report({"ERROR"}, f"Could not add {variant_id}")
            return {"CANCELLED"}

        _move_into_place(new_object, old_object)
        for prop in _KEPT_PROPS:
            if prop in old_object:
                new_object[prop] = old_object[prop]

        # keep it as the primary cockpit or landing bay
        optimiser = getattr(context.scene, "charon_optimiser", None)
        if optimiser is not None:
            for slot in ("cockpit", "landing_bay"):
                if getattr(optimiser, slot, None) == old_object:
                    setattr(optimiser, slot, new_object)

        # select first: removing a selected object breaks the selection list
        selection.select_only(new_object)
        bpy.data.objects.remove(old_object, do_unlink=True)
        self.report({"INFO"}, f"Replaced {current_id} with {variant_id}")
        return {"FINISHED"}


classes = (
    ReplaceWithVariant,
)
