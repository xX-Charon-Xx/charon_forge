import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty

from .. import materials
from ..utils import icon_utils, optimiser_utils
from . import asset_browser_presentation


# Roughly 400px at blender's default ui scale - narrower than the add row
# popup, this one is a plain read out plus a rename field rather than
# something to search in.
EDIT_POPUP_WIDTH = 800

# How many rows the part list inside the edit popup shows before scrolling.
PART_LIST_ROWS = 15

# Roughly 700px at blender's default ui scale, which is what invoke_popup
# takes - it has no dpi aware unit, unlike a popover's bl_ui_units_x.
ADD_ROW_POPUP_WIDTH = 700



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
    """Reorder the scene's parts now: parts in the priority list first, in
    its order, then everything else"""

    bl_idname = "object.charon_optimise_now"
    bl_label = "Optimise Now"

    def execute(self, context):
        from ..builder import get_builder

        count = optimiser_utils.reorder_scene_objects(get_builder())
        self.report({"INFO"}, f"Reordered {count} part(s)")
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

class PriorityListDeletePart(bpy.types.Operator):
    """Remove one part from a priority group"""

    bl_idname = "object.charon_priority_list_delete_part"
    bl_label = "Remove Part"
    bl_options = {"INTERNAL"}

    index: IntProperty()
    object_id: StringProperty()

    def execute(self, context):
        priority_list = optimiser_utils.get_priority_list()
        if 0 <= self.index < len(priority_list):
            parts = optimiser_utils.get_group_parts(priority_list[self.index])
            parts.pop(self.object_id, None)
            optimiser_utils.save_priority_list(priority_list)

        optimiser = context.scene.charon_optimiser

        # a no-op if this id was never staged (it was an already saved part
        # being removed) - but if it was, the row rebuilt below would only
        # come back on OK unless it is dropped here too
        for staged_index, staged in enumerate(optimiser.priority_staged_additions):
            if staged.object_id == self.object_id:
                optimiser.priority_staged_additions.remove(staged_index)
                break

        # the edit popup's list is a scene collection, not read live off
        # disk each draw (see PriorityPartItem) - rebuild it so the removed
        # row is actually gone rather than just gone from the saved file.
        # Rebuilding from disk drops every staged preview row along with it,
        # so they are added back in - refresh_priority_part_list has no way
        # to know about staged, unsaved parts on its own.
        optimiser.refresh_priority_part_list(self.index)
        for staged in optimiser.priority_staged_additions:
            preview = optimiser.priority_part_list.add()
            preview.object_id = staged.object_id
            preview.nice_name = staged.nice_name

        for area in context.screen.areas:
            area.tag_redraw()

        return {"FINISHED"}


class PriorityListStagePart(bpy.types.Operator):
    """Move one search result into the group being edited

    Staged only - the priority list on disk is not touched until the edit
    popup's OK is pressed, see PriorityListEdit.execute.
    """

    bl_idname = "object.charon_priority_list_stage_part"
    bl_label = "Add Part"
    bl_options = {"INTERNAL"}

    object_id: StringProperty()
    nice_name: StringProperty()

    def execute(self, context):
        optimiser = context.scene.charon_optimiser
        optimiser.stage_priority_part(self.object_id, self.nice_name)

        for area in context.screen.areas:
            area.tag_redraw()

        return {"FINISHED"}


def _priority_search_category_items(self, context):
    """Reuse AssetBrowser's own category enum items.

    Both browser drop-downs the search side of the edit popup draws are
    read only views into whichever category/sub-category are already
    selected in the asset browser itself - the update happens once
    selection is confirmed, via PrioritySearchSelectCategory/SubCategory's
    execute rather than the browser's own update callbacks, so the search
    results collection is written from an operator rather than draw().
    """
    asset_browser = context.scene.nms_asset_browser
    return asset_browser.get_categories()


def _priority_search_sub_category_items(self, context):
    asset_browser = context.scene.nms_asset_browser
    return asset_browser.extract_enum_sub_categories()


class PrioritySearchSelectCategory(bpy.types.Operator):
    """Choose which category the search side of the edit popup browses"""

    bl_idname = "object.charon_priority_search_select_category"
    bl_label = "Category"
    bl_options = {"INTERNAL"}
    bl_property = "category"

    category: EnumProperty(items=_priority_search_category_items)

    def execute(self, context):
        asset_browser = context.scene.nms_asset_browser
        asset_browser.asset_browser_caterogies = self.category

        optimiser = context.scene.charon_optimiser
        optimiser.refresh_priority_search_results()

        for area in context.screen.areas:
            area.tag_redraw()

        return {"FINISHED"}

class PrioritySearchSelectSubCategory(bpy.types.Operator):
    """Choose which sub-category the search side of the edit popup browses"""

    bl_idname = "object.charon_priority_search_select_sub_category"
    bl_label = "Sub-Category"
    bl_options = {"INTERNAL"}
    bl_property = "sub_category"

    sub_category: EnumProperty(items=_priority_search_sub_category_items)

    def execute(self, context):
        asset_browser = context.scene.nms_asset_browser
        asset_browser.asset_browser_sub_caterogies = self.sub_category

        optimiser = context.scene.charon_optimiser
        optimiser.refresh_priority_search_results()

        for area in context.screen.areas:
            area.tag_redraw()

        return {"FINISHED"}

class PriorityListEdit(bpy.types.Operator):
    """Show every part in this priority group, and rename it"""

    bl_idname = "object.charon_priority_list_edit"
    bl_label = "Edit Priority Group"
    bl_options = {"INTERNAL"}

    index: IntProperty()
    # No update callback: invoke_props_dialog gives a real OK/Cancel, so
    # typing here only edits the operator's own copy - execute() is the one
    # place that writes it out, and only OK reaches execute at all.
    group_name: StringProperty(name="Name")

    def invoke(self, context, event):
        priority_list = optimiser_utils.get_priority_list()
        if 0 <= self.index < len(priority_list):
            self.group_name = optimiser_utils.get_group_name(
                priority_list[self.index]
            )

        # has to happen here rather than in draw(): draw() runs during
        # popup redraws, where blender does not let a scene collection's
        # writes stick - the same restriction that ruled out a UIList for
        # the group list this popup is opened from.
        optimiser = context.scene.charon_optimiser
        optimiser.refresh_priority_part_list(self.index)
        optimiser.clear_priority_search()

        return context.window_manager.invoke_props_dialog(
            self, width=EDIT_POPUP_WIDTH
        )

    def execute(self, context):
        # only reached on OK - Cancel (or Esc) never calls this, so a
        # rename or a staged addition left mid edit is simply discarded
        optimiser = context.scene.charon_optimiser

        priority_list = optimiser_utils.get_priority_list()
        if 0 <= self.index < len(priority_list):
            group = priority_list[self.index]
            group["name"] = self.group_name.strip() or optimiser_utils.UNNAMED_GROUP_NAME

            parts = optimiser_utils.get_group_parts(group)
            for staged in optimiser.priority_staged_additions:
                parts[staged.object_id] = staged.nice_name
            group["parts"] = parts

            optimiser_utils.save_priority_list(priority_list)

        optimiser.clear_priority_search()
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        optimiser = context.scene.charon_optimiser

        priority_list = optimiser_utils.get_priority_list()
        if self.index < 0 or self.index >= len(priority_list):
            layout.label(text="This group no longer exists", icon="ERROR")
            return

        layout_row = layout.row(align=False)

        # left: the group's current parts, with a remove button each
        elements_list_column = layout_row.column(align=True)
        elements_list_column.label(text="Title")
        elements_list_column.prop(self, "group_name", text="")
        elements_list_column.separator()

        if optimiser.priority_staged_additions:
            elements_list_column.label(
                text=f"+ {len(optimiser.priority_staged_additions)} staged, added on OK"
            )
        else:
            elements_list_column.label(
                text=f"Objects List"
            )
            
        if not optimiser.priority_part_list:
            elements_list_column.label(text="No Items")

        # always drawn, even empty - an empty template_list still renders as
        # a box, which reads better here than the column jumping around as
        # rows are added and removed
        elements_list_column.template_list(
            "CHARON_UL_priority_part_list", "",
            optimiser, "priority_part_list",
            optimiser, "priority_part_list_index",
            rows=PART_LIST_ROWS + 1,
        )

        # right: search for parts to stage into the group above
        search_list_column = layout_row.column(align=True)
        search_list_column.label(text="Add Parts")
        search_list_column.prop(
            optimiser, "priority_search_query", text="", icon="VIEWZOOM"
        )
        search_list_column.separator()

        query = (optimiser.priority_search_query or "").strip()

        # category / sub-category browse, same "list view" layout as the
        # asset browser's own (Category label + dropdown, Sub-Category label
        # + dropdown side by side) - only meaningful once the search box is
        # empty, browsing is what fills the list in that case
        if not query:
            asset_browser = context.scene.nms_asset_browser
            browse_row = search_list_column.row(align=True)

            category_column = browse_row.column(align=True)
            category_column.label(text="Category")
            category_column.operator_menu_enum(
                PrioritySearchSelectCategory.bl_idname, "category",
                text=asset_browser.asset_browser_caterogies or "Category",
            )

            sub_category_column = browse_row.column(align=True)
            sub_category_column.label(text="Sub-Category")
            sub_category_column.operator_menu_enum(
                PrioritySearchSelectSubCategory.bl_idname, "sub_category",
                text=asset_browser.asset_browser_sub_caterogies or "All",
            )

            search_list_column.separator()

        if query and len(query) < 3:
            search_list_column.label(text="Type at least three characters to search")
        elif not optimiser.priority_search_result_list:
            search_list_column.label(text="No Items")

        # same list template as the left column, with an add button instead
        # of a remove button - see
        # optimiser_presentation.CHARON_UL_priority_search_result_list
        search_list_column.template_list(
            "CHARON_UL_priority_search_result_list", "",
            optimiser, "priority_search_result_list",
            optimiser, "priority_search_result_list_index",
            rows=PART_LIST_ROWS,
        )





class PriorityListAddRow(bpy.types.Operator):
    """Add a new priority group"""

    bl_idname = "object.charon_priority_list_add_row"
    bl_label = "Add Row"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        # start on a clean search rather than whatever the asset browser or
        # the header menu was last looking at
        asset_browser = context.scene.nms_asset_browser
        asset_browser.asset_broser_search_query = ""
        return context.window_manager.invoke_popup(
            self, width=ADD_ROW_POPUP_WIDTH
        )

    def execute(self, context):
        optimiser = context.scene.charon_optimiser
        optimiser.add_priority_group()
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        asset_browser = context.scene.nms_asset_browser

        search_column = layout.column(align=True)
        search_column.label(text="Search Items")
        # the same property the header menu searches on, so its update
        # callback does the filtering for us - see AssetBrowser.on_search_entered
        search_column.prop(
            asset_browser, "asset_broser_search_query", text="", icon="VIEWZOOM"
        )

        layout.separator()

        if asset_browser.enum_asset_browser_what_to_display != "search":
            layout.label(text="Type at least three characters to search")
            return

        search_data = asset_browser.get_search_results()
        if not search_data:
            layout.label(text="No Items")
            return

        try:
            pcoll = icon_utils.get_asset_icons_pcoll()
        except KeyError:
            pcoll = None

        results_row = layout.row(align=True)
        for sub_category, object_ids in search_data.items():
            asset_browser_presentation.draw_sub_category(
                pcoll=pcoll,
                container=results_row,
                label=sub_category,
                elements_list=object_ids,
                number_of_columns=4,
                icon_size=2,
                grid_type="Other",
                show_title=False,
            )


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
    PriorityListDeletePart,
    PriorityListStagePart,
    PrioritySearchSelectCategory,
    PrioritySearchSelectSubCategory,
    PriorityListEdit,
    PriorityListAddRow,
    PriorityListReset,
)
