import bpy
from bpy.types import Panel

from .optimiser_operators import (OptimiseMaterials, PriorityListDelete,
                                  PriorityListMove)


class CHARON_UL_priority_list(bpy.types.UIList):
    """Rows for reordering/deleting priority groups, one row per group."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=f"{item.order}: {item.summary}", translate=False)

        controls_row = row.row(align=True)
        controls_row.alignment = "RIGHT"

        up_button = controls_row.operator(
            PriorityListMove.bl_idname, text="", icon="TRIA_UP", emboss=False
        )
        up_button.index = index
        up_button.direction = "UP"

        down_button = controls_row.operator(
            PriorityListMove.bl_idname, text="", icon="TRIA_DOWN", emboss=False
        )
        down_button.index = index
        down_button.direction = "DOWN"

        controls_row.separator()

        delete_button = controls_row.operator(
            PriorityListDelete.bl_idname, text="", icon="X", emboss=False
        )
        delete_button.index = index


# Optimiser Panel ---
class CHARON_PT_optimiser_panel(Panel):
    bl_idname = "CHARON_PT_optimiser_panel"
    bl_label = "Optimiser"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Charon Forge"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout
        main_box = layout.column(align=True)

        info_row = main_box.row(align=True)
        info_row.label(text="Merge duplicate part meshes to shrink file size")

        action_row = main_box.row(align=True)
        action_row.scale_y = 1.2
        action_row.operator(
            OptimiseMaterials.bl_idname,
            icon="MOD_DECIM",
        )

        optimiser = context.scene.charon_optimiser
        if optimiser.optimise_count:
            main_box.label(text=f"Optimised {optimiser.optimise_count} time(s) this session")

        layout.separator()
        priority_box = layout.column(align=True)
        priority_box.label(text="Priority List")

        if not optimiser.priority_list:
            optimiser.refresh_priority_list()

        priority_box.template_list(
            "CHARON_UL_priority_list", "",
            optimiser, "priority_list",
            optimiser, "priority_list_index",
            rows=4,
        )


classes = (
    CHARON_UL_priority_list,
    CHARON_PT_optimiser_panel,
)
