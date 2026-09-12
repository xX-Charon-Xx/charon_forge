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


class OptimiseNow(bpy.types.Operator):
    """Optimise the scene now"""

    bl_idname = "object.charon_optimise_now"
    bl_label = "Optimise Now"

    def execute(self, context):
        # dummy for now - the panel just needs the button to exist
        self.report({"INFO"}, "Optimise Now (not implemented)")
        return {"FINISHED"}


class PriorityListMove(bpy.types.Operator):
    """Move a priority group up or down in the priority list"""

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
    """Remove a priority group from the priority list"""

    bl_idname = "object.charon_priority_list_delete"
    bl_label = "Delete Priority Group"
    bl_options = {"INTERNAL"}

    index: IntProperty()

    def execute(self, context):
        optimiser = context.scene.charon_optimiser
        optimiser.delete_priority_group(self.index)
        return {"FINISHED"}


class PriorityListEdit(bpy.types.Operator):
    """Edit this priority group"""

    bl_idname = "object.charon_priority_list_edit"
    bl_label = "Edit Priority Group"
    bl_options = {"INTERNAL"}

    index: IntProperty()

    def execute(self, context):
        # dummy for now - the row just needs the button to exist
        self.report({"INFO"}, f"Edit priority group {self.index} (not implemented)")
        return {"FINISHED"}


class PriorityListReset(bpy.types.Operator):
    """Discard your changes and go back to the priority list the addon ships with"""

    bl_idname = "object.charon_priority_list_reset"
    bl_label = "Reset Priority List"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        optimiser = context.scene.charon_optimiser
        optimiser.reset_priority_list()
        self.report({"INFO"}, "Priority list reset to the shipped default")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


classes = (
    OptimiseMaterials,
    OptimiseNow,
    PriorityListMove,
    PriorityListDelete,
    PriorityListEdit,
    PriorityListReset,
)
