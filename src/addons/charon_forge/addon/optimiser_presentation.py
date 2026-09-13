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
    """A horizontal strip of icons for the first few parts of a group.

    Object ids carry a "^" prefix in the priority list that the icon files
    do not have, so it is stripped before the lookup - see
    icon_utils.load_asset_icons.
    """
    parts = optimiser_utils.get_group_parts(group)

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

        if slot >= len(parts):
            # blank lines holding the cell open, so the filled ones keep
            # their size instead of stretching to share the row. A
            # template_icon is about `scale` lines tall, so it takes that
            # many blank labels to match the height of a filled cell.
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
    """Search results to add to the group being edited, with an add button each.

    Same row layout as CHARON_UL_priority_part_list - icon plus name - with
    an ADD button in place of the remove button, since this list is search
    results rather than the group's own current parts.
    """

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
        description_icon_row.alignment = "CENTER"
        description_icon_row.template_icon(
            icon_value=icon_utils.get_icon_id("app_icon"),
            scale=2,
        )
        description_column = description_row.column(align=True)
        description_column.alignment = "CENTER"
        description_column.label(text="If checked, automatically order")
        description_column.label(text="objects in optimal way")
        
        if prefs is not None:
            description_column.separator(factor = 2)
            # a checkbox drawn as a button - the label has to be passed in to say
            # On/Off, prop() would otherwise use the property's own name for both
            # states. Stored in preferences (per user, across restarts) rather
            # than on scene.charon_optimiser - see addon_preferences.py.
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

    def draw(self, context):
        layout = self.layout

        # Reset sits in the body rather than draw_header_preset: that draws
        # even while the panel is collapsed, and blender does not expose a
        # sub-panel's expand state to python to gate it on directly. draw()
        # itself only runs while expanded, so putting it here is what
        # actually hides it.
        prefs = addon_preferences.get_addon_preferences()
        preview_row = layout.row(align=True)
        if prefs is not None:
            preview_row.prop(prefs, "show_preview", text="Show Preview")
        preview_row.operator(
            PriorityListReset.bl_idname, text="Reset", icon="LOOP_BACK"
        )

        # Drawn straight from the saved list rather than through a UIList and
        # its scene collection: a plain loop reads fine while the scene is
        # read only for drawing, which is what made the collection based
        # version come up empty.
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
