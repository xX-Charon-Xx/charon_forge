import bpy

from ..objects.group import Group
from ..objects.part import Part
from ..objects.sphere import Sphere


def sphere_source_problem(obj):
    """Why an object can't be made into a sphere, or None if it can."""
    if obj is None:
        return "Select a part first"
    if obj.type != "MESH" or Part.PROP_OBJECT_ID not in obj or Group.PROP_GROUP_ID in obj:
        return "The selected object is not a part"
    if obj.children:
        return "Parts with attached pieces can't be made into a sphere"
    return None


def _select_only(context, objects):
    for obj in context.selected_objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    if objects:
        context.view_layer.objects.active = objects[0]


class CreateSphere(bpy.types.Operator):
    """Turn the selected part into a sphere of copies of it, one object you can keep adjusting"""

    bl_idname = "object.charon_forge_create_sphere"
    bl_label = "Create Sphere"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        problem = sphere_source_problem(context.active_object)
        if problem:
            cls.poll_message_set(problem)
            return False
        return True

    def execute(self, context):
        sphere = Sphere.create(context.active_object)
        _select_only(context, [sphere])
        message = sphere.charon_sphere.message
        if message:
            self.report({"WARNING"}, message)
        return {"FINISHED"}


class SplitSphere(bpy.types.Operator):
    """Break the sphere into its separate parts. It can't be adjusted after"""

    bl_idname = "object.charon_forge_split_sphere"
    bl_label = "Split into Parts"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return Sphere.is_sphere(context.active_object)

    def execute(self, context):
        from ..builder import get_builder

        parts = Sphere.split(context.active_object, get_builder())
        _select_only(context, parts)
        self.report({"INFO"}, f"Split into {len(parts)} part(s)")
        return {"FINISHED"}


classes = (
    CreateSphere,
    SplitSphere,
)
