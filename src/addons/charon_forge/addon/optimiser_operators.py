import bpy
from bpy.props import EnumProperty, IntProperty

from .. import materials


class OptimiseMaterials(bpy.types.Operator):
    """Make flat parts with the same ObjectID and UserData share one mesh"""

    bl_idname = "object.charon_optimise_materials"
    bl_label = "Optimise Materials"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        materials.optimise_materials()
        optimiser = context.scene.charon_optimiser
        count = optimiser.optimise()
        self.report({"INFO"}, f"Optimised materials ({count} time(s) this session)")
        return {"FINISHED"}


class PriorityListMove(bpy.types.Operator):
    """Move a priority group up or down in priority_list.json"""

    bl_idname = "object.charon_priority_list_move"
    bl_label = "Move Priority Group"
    bl_options = {"INTERNAL"}

    index: IntProperty()
    direction: EnumProperty(
        items=[("UP", "Up", ""), ("DOWN", "Down", "")],
        default="UP",
    )

    def execute(self, context):
        optimiser = context.scene.charon_optimiser
        optimiser.move_priority_group(self.index, self.direction)
        return {"FINISHED"}


class PriorityListDelete(bpy.types.Operator):
    """Remove a priority group from priority_list.json"""

    bl_idname = "object.charon_priority_list_delete"
    bl_label = "Delete Priority Group"
    bl_options = {"INTERNAL"}

    index: IntProperty()

    def execute(self, context):
        optimiser = context.scene.charon_optimiser
        optimiser.delete_priority_group(self.index)
        return {"FINISHED"}


classes = (
    OptimiseMaterials,
    PriorityListMove,
    PriorityListDelete,
)
