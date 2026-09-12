import bpy
from bpy.types import Panel

from ..utils import dictionary, icon_utils
from .optimiser_operators import (OptimiseNow, PriorityListEdit,
                                  PriorityListMove, PriorityListReset)


# How many of a group's parts get an icon on the row.
PREVIEW_COUNT = 4
PREVIEW_ICON_SCALE = 2


def draw_preview_icons(container, group):
    """A horizontal strip of icons for the first few parts of a group.

    Object ids carry a "^" prefix in the priority list that the icon files
    do not have, so it is stripped before the lookup - see
    icon_utils.load_asset_icons.
    """
    # raises if register_icons has not run yet, which must not take the
    # whole panel down with it
    try:
        pcoll = icon_utils.get_asset_icons_pcoll()
    except KeyError:
        pcoll = None

    # a grid rather than a row of columns: every cell gets the same width
    # whether or not it has an icon in it, so a short group does not end up
    # with wide icons and a narrow gap
    icons_grid = container.grid_flow(
        row_major=True,
        columns=PREVIEW_COUNT,
        even_columns=True,
        even_rows=True,
        align=False,
    )

    for slot in range(PREVIEW_COUNT):
        cell = icons_grid.column(align=True)

        if slot >= len(group):
            # blank lines holding the cell open, so the filled ones keep
            # their size instead of stretching to share the row. A
            # template_icon is about `scale` lines tall, so it takes that
            # many blank labels to match the height of a filled cell.
            for _ in range(PREVIEW_ICON_SCALE):
                cell.label(text="")
            continue

        icon_key = list(group)[slot].lstrip("^")
        if pcoll is not None and icon_key in pcoll:
            icon_value = pcoll[icon_key].icon_id
        else:
            # same stand in the asset browser grid falls back to
            icon_value = bpy.types.UILayout.bl_rna.functions["label"].parameters[
                "icon"
            ].enum_items["MONKEY"].value

        cell.template_icon(icon_value=icon_value, scale=PREVIEW_ICON_SCALE)


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
        optimiser = context.scene.charon_optimiser

        # a checkbox drawn as a button - the label has to be passed in to say
        # On/Off, prop() would otherwise use the property's own name for both
        # states
        auto_on = optimiser.auto_optimise
        toggle_row = layout.row(align=True)
        toggle_row.alert = not auto_on
        #toggle_row.scale_y = 1.2
        toggle_row.prop(
            optimiser,
            "auto_optimise",
            text="Auto Optimise On" if auto_on else "Auto Optimise Off",
            icon="CHECKBOX_HLT" if auto_on else "CHECKBOX_DEHLT",
            toggle=True,
        )
        

        # what the checkbox above does, in its own column so the button
        # scaling does not stretch the text out. Red while the toggle is
        # off, to point at the thing that is not happening.
        description_column = layout.column(align=True)
        description_column.scale_y = 0.8
        description_column.label(text="If checked, automatically order")
        description_column.label(text="objects in optimal way")
        layout.separator()
        
        action_row = layout.row(align=True)
        #action_row.scale_y = 1.2
        action_row.operator(OptimiseNow.bl_idname, icon="MOD_DECIM")


class CHARON_PT_priority_list_panel(Panel):
    """The priority list, as a collapsible section of the optimiser panel.

    A child panel rather than a box with a toggle property: blender gives
    it a real collapse arrow and remembers the open/closed state itself,
    with nothing to store on the scene.
    """

    bl_idname = "CHARON_PT_priority_list_panel"
    bl_label = "Priority List"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Charon Forge"
    bl_context = "objectmode"
    bl_parent_id = CHARON_PT_optimiser_panel.bl_idname
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header_preset(self, context):
        # the right hand end of the header, where blender puts a panel's
        # own controls
        self.layout.operator(
            PriorityListReset.bl_idname, text="", icon="LOOP_BACK", emboss=False
        )

    def draw(self, context):
        layout = self.layout

        # Drawn straight from the saved list rather than through a UIList and
        # its scene collection: a plain loop reads fine while the scene is
        # read only for drawing, which is what made the collection based
        # version come up empty.
        priority_list = dictionary.get_cached_priority_list()

        if not priority_list:
            layout.box().label(text="No Items")
            return

        list_column = layout.column(align=True)
        for index, group in enumerate(priority_list):
            group_box = list_column.box()
            item_column = group_box.column(align=True)

            header_row = item_column.row(align=True)
            part_count = len(group)
            header_row.label(
                text=f"Order : {index}",
                translate=False,
            )

            controls_row = header_row.row(align=True)
            controls_row.alignment = "RIGHT"
            
            controls_row.label(
                text = f" {part_count} "
                f"{'pt' if part_count == 1 else 'pts'}  "
            )

            edit_button = controls_row.operator(
                PriorityListEdit.bl_idname, text="Edit", icon="GREASEPENCIL", emboss=True
            )
            edit_button.index = index

            controls_row.separator()

            # embossed, so the pair reads as the one control that actually
            # changes the order
            move_row = controls_row.row(align=True)
            up_button = move_row.operator(
                PriorityListMove.bl_idname, text="", icon="TRIA_UP", emboss=True
            )
            up_button.index = index
            up_button.direction = "UP"

            down_button = move_row.operator(
                PriorityListMove.bl_idname, text="", icon="TRIA_DOWN", emboss=True
            )
            down_button.index = index
            down_button.direction = "DOWN"

            draw_preview_icons(item_column, group)


classes = (
    CHARON_PT_optimiser_panel,
    CHARON_PT_priority_list_panel,
)
