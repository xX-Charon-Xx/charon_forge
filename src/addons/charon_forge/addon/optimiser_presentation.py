import bpy
from bpy.types import Panel

from .. import addon_preferences
from ..utils import icon_utils, optimiser_utils
from .optimiser_operators import (OptimiseNow, PriorityListAddRow,
                                  PriorityListDeletePart, PriorityListEdit,
                                  PriorityListMove, PriorityListReset,
                                  PriorityListStagePart)


# How many of a group's parts get an icon on the row.
PREVIEW_COUNT = 4
PREVIEW_ICON_SCALE = 2


def draw_preview_icons(container, group):
    """A horizontal strip of icons for the first few parts of a group."""
    parts = optimiser_utils.get_group_parts(group)

    # raises if register_icons has not run yet, which must not take the
    # whole panel down with it
    try:
        pcoll = icon_utils.get_asset_icons_pcoll()
    except KeyError:
        pcoll = None

    # a grid, so every cell gets the same width whether or not it has an icon
    icons_grid = container.grid_flow(
        row_major=True,
        columns=PREVIEW_COUNT,
        even_columns=True,
        even_rows=True,
        align=False,
    )

    for slot in range(PREVIEW_COUNT):
        cell = icons_grid.column(align=True)

        if slot >= len(parts):
            # blank labels keep the empty cell as tall as a filled one
            for _ in range(PREVIEW_ICON_SCALE):
                cell.label(text="")
            continue

        icon_key = list(parts)[slot].lstrip("^")
        if pcoll is not None and icon_key in pcoll:
            icon_value = pcoll[icon_key].icon_id
        else:
            # same stand in the asset browser grid falls back to
            icon_value = bpy.types.UILayout.bl_rna.functions["label"].parameters[
                "icon"
            ].enum_items["MONKEY"].value

        cell.template_icon(icon_value=icon_value, scale=PREVIEW_ICON_SCALE)


class CHARON_UL_priority_part_list(bpy.types.UIList):
    """Rows for one priority group's parts, with a remove button each."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)

        try:
            pcoll = icon_utils.get_asset_icons_pcoll()
        except KeyError:
            pcoll = None

        # object ids carry a "^" prefix that icon files do not have - see
        # icon_utils.load_asset_icons
        icon_key = item.object_id.lstrip("^")
        if pcoll is not None and icon_key in pcoll:
            row.label(text=item.nice_name, icon_value=pcoll[icon_key].icon_id)
        else:
            row.label(text=item.nice_name, icon="MONKEY")

        remove_button = row.operator(
            PriorityListDeletePart.bl_idname, text="", icon="TRASH", emboss=False
        )
        remove_button.object_id = item.object_id
        # data is the Optimiser instance this list is drawn from - see
        # PriorityListEdit.draw, which passes optimiser as the list's data
        remove_button.index = data.priority_part_list_group_index


class CHARON_UL_priority_search_result_list(bpy.types.UIList):
    """Search results to add to the group being edited, with an add button each."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)

        try:
            pcoll = icon_utils.get_asset_icons_pcoll()
        except KeyError:
            pcoll = None

        icon_key = item.object_id.lstrip("^")
        if pcoll is not None and icon_key in pcoll:
            row.label(text=item.nice_name, icon_value=pcoll[icon_key].icon_id)
        else:
            row.label(text=item.nice_name, icon="MONKEY")

        add_button = row.operator(
            PriorityListStagePart.bl_idname, text="", icon="ADD", emboss=False
        )
        add_button.object_id = item.object_id
        add_button.nice_name = item.nice_name


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
        prefs = addon_preferences.get_addon_preferences()

        # scaling does not stretch the text out. Red while the toggle is
        # off, to point at the thing that is not happening.
        description_row = layout.row(align = True)
        description_row.scale_y = 0.6
        description_icon_row = description_row.row(align = True)
        description_icon_row.scale_x = 1.1
        #description_icon_row.alignment = "CENTER"
        description_icon_row.template_icon(
            icon_value=icon_utils.get_icon_id("optimisation"),
            scale=3,
        )
        description_column = description_row.column(align=True)
        description_column.separator()
        description_column.label(text="If checked, automatically order")
        description_column.label(text="objects in optimal way")
        
        if prefs is not None:
            description_column.separator(factor = 2)
            # a checkbox drawn as a button, with its own On/Off label;
            # stored in preferences so it lasts across restarts
            auto_on = prefs.auto_optimise
            toggle_row = description_column.row(align=True)
            toggle_row.alert = not auto_on
            toggle_row.scale_y = 2
            toggle_row.prop(
                prefs,
                "auto_optimise",
                text="Auto Optimise is On" if auto_on else "Auto Optimise is Off",
                icon="CHECKBOX_HLT" if auto_on else "CHECKBOX_DEHLT",
                toggle=True,
            )

            description_column.separator()
            action_row = description_column.row(align=True)
            action_row.scale_y = 1.6
            action_row.operator(
                OptimiseNow.bl_idname,
                #icon="MOD_DECIM"
            )

            # the corvette's main parts - each field searches the scene and
            # has an eyedropper
            optimiser = context.scene.charon_optimiser
            description_column.separator()
            description_column.separator()
            primary_row = description_column.row(align=True)
            primary_row.scale_y = 1.6
            primary_row.prop(optimiser, "use_primary_parts")
            if optimiser.use_primary_parts:
                parts_col = description_column.column(align=True)
                parts_col.scale_y = 2
                parts_col.prop(optimiser, "cockpit")
                parts_col.prop(optimiser, "landing_bay")


class CHARON_PT_priority_list_panel(Panel):
    """The priority list, as a collapsible section of the optimiser panel."""

    bl_idname = "CHARON_PT_priority_list_panel"
    bl_label = "Priority List"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Charon Forge"
    bl_context = "objectmode"
    bl_parent_id = CHARON_PT_optimiser_panel.bl_idname
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout

        # Reset is in the body, not the header, so it hides while collapsed
        prefs = addon_preferences.get_addon_preferences()
        preview_row = layout.row(align=True)
        if prefs is not None:
            preview_row.prop(prefs, "show_preview", text="Show Preview")
        preview_row.operator(
            PriorityListReset.bl_idname, text="Reset", icon="LOOP_BACK"
        )

        # drawn straight from the saved list; a UIList's scene collection came up empty
        priority_list = optimiser_utils.get_cached_priority_list()

        if not priority_list:
            layout.box().label(text="No Items")

        list_column = layout.column(align=True)
        for index, group in enumerate(priority_list):
            group_box = list_column.box()
            item_column = group_box.column(align=True)

            header_row = item_column.row(align=True)
            part_count = len(optimiser_utils.get_group_parts(group))
            header_row.label(
                text=f"{index}.  {optimiser_utils.get_group_name(group)}",
                translate=False,
            )

            controls_row = header_row.row(align=True)
            controls_row.alignment = "RIGHT"
            
            controls_row.label(
                text = f" {part_count} "
                f"{'pt' if part_count == 1 else 'pts'}  "
            )

            edit_button = controls_row.operator(
                PriorityListEdit.bl_idname, text="", icon="GREASEPENCIL", emboss=False
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

            if prefs is not None and prefs.show_preview:
                draw_preview_icons(item_column, group)

        layout.separator()
        layout.operator(PriorityListAddRow.bl_idname, icon="ADD")


classes = (
    CHARON_UL_priority_part_list,
    CHARON_UL_priority_search_result_list,
    CHARON_PT_optimiser_panel,
    CHARON_PT_priority_list_panel,
)
